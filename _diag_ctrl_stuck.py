# -*- coding: utf-8 -*-
"""探针：悬停加高动画是否会在「换行触发的 _relayout」打断后卡在半路。

不再用 setCurrentTime 跳帧，改用真实时间泵 processEvents —— 烟测跳帧看不到
「动画中途被打断后没走完」这类时序 bug。
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import _cfg_sandbox
_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

import lyrics_overlay as L
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPropertyAnimation, QVariantAnimation

app = QApplication(sys.argv)
ov = L.LyricOverlay(L.MediaWatcher())
ov.show()

# 伪造一首歌：短句 -> 长句（带翻译） -> 短句，让 _pill_size 有明显变化
ov.song = {"title": "测试歌曲", "artist": "测试歌手", "source": "qq", "cover": None}
ov.lines = [[0.0, "第一句歌词"], [2.0, "这是一句非常非常长用来撑宽窗口的歌词内容等等等"],
            [5.0, "短句"], [8.0, "末句"]]
ov.words = {}
ov.trans = [[0.0, "line one"], [2.0, "a much longer translated line here"], [5.0, "short"], [8.0, "end"]]
ov._trans_map = ov._build_trans_map()
ov.status = "PLAYING"

_pos = {"t": 0.0}
ov._lyric_pos = lambda: _pos["t"]

# ---- 追踪：谁动了 _hovered / _ctrl_anim ----
_real_on_ctrl = ov._on_ctrl_anim
_real_animate = ov._animate_ctrl


def _trace_on_ctrl(v):
    if v <= 0.0 and ov._hovered:
        import traceback
        print(">>> _on_ctrl_anim(%.3f) 复位 hovered, 调用栈:" % v)
        for ln in traceback.format_stack(limit=6)[:-1]:
            print("    " + ln.strip().replace("\n", " <- "))
    _real_on_ctrl(v)


def _trace_animate(target):
    print(">>> _animate_ctrl(%.2f)  当前 ctrl_t=%.3f hovered=%s" % (
        target, ov._ctrl_t, ov._hovered))
    _real_animate(target)


ov._on_ctrl_anim = _trace_on_ctrl
ov._animate_ctrl = _trace_animate
# 信号连接持有的是原始绑定方法，需重连才能追到 valueChanged 路径
ov._ctrl_anim.valueChanged.disconnect()
ov._ctrl_anim.valueChanged.connect(_trace_on_ctrl)


def pump(sec):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def snap(tag):
    m = ov._margin()
    cr = ov._ctrl_rect()
    ph = ov._pill_size()[1]
    exp_h = ph + 2 * m + ov._ctrl_reserve()
    print("%-28s win=%dx%d layout=%s exp_h=%.0f capsTop=%.1f capsBot=%.1f "
          "inside=%s sizeAnim=%s ctrlT=%.2f hovered=%s lineAnim=%s" % (
              tag, ov.width(), ov.height(), ov._layout_size, exp_h,
              cr.top(), cr.bottom(),
              cr.bottom() <= ov.height() and cr.top() >= 0,
              ov._size_anim.state() == QPropertyAnimation.Running,
              ov._ctrl_t, ov._hovered,
              ov._line_anim.state() == QVariantAnimation.Running))


print("=== 场景A：悬停加高动画进行到一半时换行 ===")
ov._cursor_global = lambda: ov.mapToGlobal(ov.rect().center())
pump(0.15)
ov._on_frame()
snap("A0 稳态(未悬停)")

# 进入悬停（enterEvent 路径）
ov.enterEvent(None)
snap("A1 enter 后立刻")

pump(0.12)          # 300ms 动画走到 ~40%
snap("A2 动画40%")

# 动画中途换行：短句 -> 长句
_pos["t"] = 2.5
ov._on_frame()
snap("A3 换行触发 _relayout")

pump(0.6)
snap("A4 泵600ms后(应已稳)")

pump(0.6)
snap("A5 再泵600ms(应已稳)")

print()
print("=== 场景B：动画中途换行两次（快速连切） ===")
ov._on_ctrl_anim(0.0)          # 先离开悬停
pump(0.5)
snap("B0 收回预留行")
ov._hovered = True
ov._relayout()
_pos["t"] = 0.5
ov._on_frame()
snap("B1 enter(短句)")
pump(0.08)
_pos["t"] = 5.5
ov._on_frame()                 # 40ms 时切到短句
snap("B2 40ms 切短句")
pump(0.06)
_pos["t"] = 8.5
ov._on_frame()                 # 100ms 再切末句
snap("B3 100ms 再切末句")
pump(0.8)
snap("B4 泵800ms后(应已稳)")

print()
print("=== 场景C：光标出窗后反复重启淡出动画，_hovered 能否归位 ===")
inside = ov.mapToGlobal(ov.rect().center())
outside = inside + __import__("PySide6.QtCore", fromlist=["QPoint"]).QPoint(3000, 3000)
ov._cursor_global = lambda: outside
t0 = time.monotonic()
while time.monotonic() - t0 < 2.0:
    ov._on_frame()
    app.processEvents()
    time.sleep(0.033)
    if not ov._hovered:
        break
print("耗时 %.2fs  _ctrl_t=%.4f  _hovered=%s  ctrlAnim=%s" % (
    time.monotonic() - t0, ov._ctrl_t, ov._hovered,
    ov._ctrl_anim.state() == QVariantAnimation.Running))
snap("C1 光标出窗2s后")
pump(0.6)
snap("C2 再泵600ms")
