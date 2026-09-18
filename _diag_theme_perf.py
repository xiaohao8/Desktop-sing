# -*- coding: utf-8 -*-
"""主题渲染性能诊断：量每种悬浮主题「每帧绘制耗时」

背景：原生浮字（第一个主题）一直很顺，其余主题（玻璃/iOS/黑胶/Spotify）
的逐字动画会卡。怀疑点：只有非 native 主题挂了 QGraphicsDropShadowEffect
（每帧对整窗做多趟高斯模糊）+ 氛围光晕（每帧整窗径向渐变）。

用法（需带 PySide6 的那个 Python）：
    python _diag_theme_perf.py                # 默认测全部 5 种主题
    python _diag_theme_perf.py glass ios      # 只测指定主题
    python _diag_theme_perf.py --glow off     # 关掉氛围光晕再测
    python _diag_theme_perf.py --seconds 2    # 每种主题采样时长

输出：每种主题的帧数 / 平均帧耗时 / 最慢帧 / 估算可支撑帧率。
不写配置、不拉守护进程，测完自动还原原配置。
"""
import json
import os
import shutil
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

CFG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                   "Desktop-sing", "config.json")
BAK = CFG + ".perfbak"
_had_cfg = os.path.exists(CFG)
if _had_cfg:
    shutil.copy2(CFG, BAK)
os.makedirs(os.path.dirname(CFG), exist_ok=True)
with open(CFG, "w", encoding="utf-8") as f:      # 干净配置：不开热键、不拉保活守护进程
    json.dump({"hotkeys": False, "keepalive": False, "idle_saver": False}, f)

import lyrics_overlay as L                                        # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402
from PySide6.QtCore import QTimer, QEvent                         # noqa: E402
from PySide6.QtGui import QPaintEvent                             # noqa: E402

ARGS = [a for a in sys.argv[1:]]
STYLES, GLOW, SECONDS, FORCE_SHADOW, ANIM = [], True, 2.0, None, None
_i = 0
while _i < len(ARGS):
    a = ARGS[_i]
    if a == "--glow":                      # on / off
        GLOW = ARGS[_i + 1].lower() in ("on", "1", "true")
        _i += 2
    elif a == "--seconds":                 # 每种主题采样多少秒
        SECONDS = float(ARGS[_i + 1])
        _i += 2
    elif a == "--shadow":                  # on / off / auto（默认按主题自身策略）
        FORCE_SHADOW = ARGS[_i + 1].lower() not in ("off", "0", "false")
        _i += 2
    elif a == "--anim":                    # 固定逐字动画，逐个量 9 种动画的开销
        ANIM = ARGS[_i + 1]
        _i += 2
    elif a in L.STYLE_NAMES:
        STYLES.append(a)
        _i += 1
    else:
        print("未知参数：%s" % a)
        sys.exit(2)
STYLES = STYLES or list(L.STYLE_NAMES.keys())

app = None

# ---- 在事件分发层打点：量「整帧真实开销」（含 paintEvent 之后的投影特效）----
# 注意：只量 paintEvent 内部是量不到 QGraphicsDropShadowEffect 的——它在
# paintEvent 返回之后才把源图做高斯模糊再合成，所以必须在 notify 里包住整个
# QEvent.Paint 的分发过程。
_stats = {"n": 0, "t": 0.0, "max": 0.0, "gaps": [], "last": 0.0, "stalled": 0}
_orig_notify = QApplication.notify


class _TimedApp(QApplication):
    def notify(self, receiver, event):
        if event.type() == QEvent.Paint and isinstance(receiver, L.LyricOverlay):
            now = time.perf_counter()
            if _stats["last"]:
                gap = now - _stats["last"]
                _stats["gaps"].append(gap)
                if gap > 0.15:                 # >150ms 没出新帧 = 肉眼可见的卡顿
                    _stats["stalled"] += 1
            _stats["last"] = now
            t0 = now
            try:
                return _orig_notify(self, receiver, event)
            finally:
                dt = time.perf_counter() - t0
                _stats["n"] += 1
                _stats["t"] += dt
                _stats["max"] = max(_stats["max"], dt)
        return _orig_notify(self, receiver, event)


app = _TimedApp(sys.argv)

ov = L.LyricOverlay(L.MediaWatcher())
ov.show()

# 假曲目 + 带逐字时间轴的歌词（不依赖真实播放器）
SONG = {"title": "性能诊断", "artist": "diag", "source": "qq", "cover": None}
LINES = [[float(i), "灯光照着我的侧脸像一场梦不留痕迹"] for i in range(0, 120, 3)]
WORDS = {}
for i in range(len(LINES)):
    t0 = float(i * 3)
    WORDS[i] = [(t0, 1.0, "灯光照着"), (t0 + 1.0, 1.0, "我的侧脸"),
                (t0 + 2.0, 1.0, "像一场梦不留痕迹")]

ov.song = SONG
ov.lines = LINES
ov.words = WORDS
ov.status = "PLAYING"
ov.glow = GLOW
ov.resize(1000, 260)
ov.anchor_pos = 0.0
ov.anchor_ts = time.monotonic()
ov._line_t = 1.0

# 被测用例：(标签, 主题, 逐字动画)。默认逐个主题；给 --anim all 则固定主题逐个动画。
if ANIM == "all":
    CASES = [(a, STYLES[0], a) for a in L.ANIM_STYLES]
    print("逐字动画开销诊断（主题固定为 %s；帧定时器 33ms；glow=%s，每种 %.1fs）"
          % (L.STYLE_NAMES[STYLES[0]], "on" if GLOW else "off", SECONDS))
else:
    CASES = [(k, k, ANIM) for k in STYLES]
    print("主题渲染性能诊断  (帧定时器 33ms；glow=%s，每主题 %.1fs)"
          % ("on" if GLOW else "off", SECONDS))
print("用例        投影   帧数  平均帧耗时  最慢帧  可支撑fps  P90间隔  最长间隔  卡顿次数  窗口尺寸")
print("-" * 92)

_state = {"i": -1}


def _next_step():
    _state["i"] += 1
    if _state["i"] >= len(CASES):
        app.quit()
        return
    label, key, anim = CASES[_state["i"]]
    ov.style_mode = key                 # 直接赋值：不走 setter，不写配置
    if anim:
        ov.anim_style = anim
    ov._apply_shadow()
    if FORCE_SHADOW is not None:        # 强制投影开关，用于 A/B 对比
        ov._shadow.setEnabled(FORCE_SHADOW)
        ov._shadow.setBlurRadius({"vinyl": 16, "glass": 22}.get(key, 26))
    ov._spans_cache.clear()
    ov._relayout()
    ov.update()
    _stats.update(n=0, t=0.0, max=0.0, gaps=[], last=0.0, stalled=0)
    QTimer.singleShot(int(SECONDS * 1000), lambda k=label: _report(k))


def _report(key):
    n, t, mx = _stats["n"], _stats["t"], _stats["max"]
    avg = (t / n * 1000.0) if n else 0.0
    shadow = "on" if ov._shadow.isEnabled() else "off"
    fps = (1000.0 / avg) if avg > 0 else 0.0
    gaps = sorted(_stats["gaps"])
    gmax = (gaps[-1] * 1000.0) if gaps else 0.0
    gp90 = (gaps[int(len(gaps) * 0.9)] * 1000.0) if gaps else 0.0
    print("%-10s  %-6s %4d  %6.2fms  %6.2fms  %6.1f  %7.2fms %7.2fms  %3d   %dx%d"
          % (key, shadow, n, avg, mx * 1000.0, fps, gp90, gmax, _stats["stalled"],
             ov.width(), ov.height()))
    _next_step()


QTimer.singleShot(300, _next_step)
app.exec()

# ---- 还原原配置 ----
try:
    if _had_cfg:
        shutil.copy2(BAK, CFG)
        os.remove(BAK)
    else:
        os.remove(CFG)
except OSError:
    pass
print("\n提示：平均帧耗时越接近/超过 33ms 就越会「卡」；>33ms 时动画被定时器挤掉，观感就是冻结。")
