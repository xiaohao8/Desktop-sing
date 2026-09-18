# -*- coding: utf-8 -*-
"""氛围屏保版式巡检：验证「文字永不被动画遮挡 / 永不被屏幕边缘裁掉」。

三层验证，互相独立：
  A. 版式层 —— 直接读 AmbientSaver._plan() 给出的几何，断言
       ① 文字块与动画带不相交   ② 文字块完整落在安全边距内
       ③ 各行基线自上而下单调、行盒不互相压字
  B. 像素层 —— 把「动画层」「文字层」分开渲染，各自求亮像素包围盒再求交。
     这一层不依赖任何坐标公式，只看真实画出来的像素（否则改了源码公式，
     版式层断言会跟着一起漂移，等于自己证明自己）。
  C. 探针自检（变异测试）—— 故意注入一个「必然冲突」的版式，确认 A/B 两层
     都真的会报错。没有这一步，一个恒真的断言和一条通过的断言长得一模一样。

换位（AOD 式 anchor 循环）会移动文字块，所以对每个风格要**遍历整个换位周期**
的多个时刻，而不是只测 t=0 —— 只在初始档位验通过是没有意义的。

性能：逐像素扫描改用 PIL（Qt 灰度转换 → 0/255 掩膜 → C 实现 getbbox），
3440x1440 一张从 ~15s 降到 ~0.025s。没有 PIL 时自动退回慢路径并只跑小尺寸。

用法：python _diag_saver_layout.py
退出码：0 全通过 / 1 有问题
"""
import math
import os
import random
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import _cfg_sandbox                                            # noqa: E402

# 先把用户配置换成固定桩（关热键 / 关保活 / 关空闲屏保），否则巡检会去抢热键、
# 拉守护进程。备份按脚本名区分 + atexit 兜底还原，见 _cfg_sandbox 模块说明。
_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

import lyrics_overlay as L                                     # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402
from PySide6.QtCore import Qt, QPointF, QRectF                 # noqa: E402
from PySide6.QtGui import (QPixmap, QPainter, QLinearGradient,  # noqa: E402
                           QColor, QBrush, QRadialGradient, QImage)

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

app = QApplication(sys.argv)
L._load_fonts()
ov = L.LyricOverlay(L.MediaWatcher())

cov = QPixmap(500, 500)
_p = QPainter(cov)
_g = QLinearGradient(0, 0, 500, 500)
_g.setColorAt(0.0, QColor("#ff8a3d"))
_g.setColorAt(0.45, QColor("#e0407a"))
_g.setColorAt(1.0, QColor("#4a3aff"))
_p.fillRect(0, 0, 500, 500, QBrush(_g))
_p.end()
ov.cover_pix = cov
ov.accent1, ov.accent2 = L.extract_accent(cov)

ov.song = {"title": "夜航西飞", "artist": "陈粒", "source": "qq"}

OUT = os.path.join(APP_DIR, "preview", "saver_layout")
os.makedirs(OUT, exist_ok=True)

STYLES = ["particle", "minimal", "bars", "orbits"]
# 慢路径（无 PIL）会把 3440x1440 拖到分钟级，故按能力裁剪尺寸表
SIZES_FAST = [(1920, 1080), (1680, 1050), (3440, 1440), (1280, 960),
              (1080, 1920), (1366, 768), (252, 142)]
SIZES_SLOW = [(1920, 1080), (1280, 960), (1366, 768), (252, 142)]
SIZES = SIZES_FAST if _HAS_PIL else SIZES_SLOW

# 面板里的实时预览尺寸：只 252x142，单独标注
PANEL_SIZE = (252, 142)

NORMAL = ("夜色温柔", "风也温柔")
LONGTEXT = ("这是一句特别特别长的歌词用来验证超长文本会被省略号截断而不会顶出屏幕左右边缘",
            "下一句同样很长很长很长很长很长很长很长很长很长很长很长很长很长很长很长")

PERIOD = L.AmbientSaver.ANCHOR_HOLD + L.AmbientSaver.ANCHOR_MOVE          # 208s
DWELL0 = PERIOD * 0.25          # 第 0 档驻留中（文字在最上）
DWELL2 = PERIOD * 2 + PERIOD * 0.25   # 第 2 档驻留中（文字在最下）
XMOVE = PERIOD + L.AmbientSaver.ANCHOR_HOLD + L.AmbientSaver.ANCHOR_MOVE * 0.5  # 过渡中
# 覆盖整个换位周期：驻留期 + 过渡期都要测
TS = [0.0, 70.0, PERIOD, PERIOD + 4.0, 1.5 * PERIOD, 1.5 * PERIOD + 6.0,
      2 * PERIOD, 2 * PERIOD + 4.0, 2 * PERIOD + 0.5 * PERIOD]
# 再抽一个「已进入渐进变暗」的晚期时刻
TS += [L.AmbientSaver.DIM_START + L.AmbientSaver.DIM_RAMP * 0.5]

# 像素层用的时刻：两个驻留端点 + 一个过渡中点（文字块的纵向极值都在这里）
TS_PIX = [DWELL0, DWELL2, XMOVE]

PROBE_THR = 8                   # 灰度阈值：>8 视为「亮像素」（等效旧版 r+g+b>24）


# ---------------------------------------------------------------- 包围盒

def bbox(pm, thr=PROBE_THR):
    """亮像素包围盒 (x0, y0, x1, y1, n)，闭区间；全黑返回 None。"""
    img = pm.toImage()
    if img.format() != QImage.Format_Grayscale8:
        img = img.convertToFormat(QImage.Format_Grayscale8)
    w, h = img.width(), img.height()
    raw = bytes(img.constBits())
    if _HAS_PIL:
        bpl = img.bytesPerLine()
        g = Image.frombytes("L", (w, h), raw, "raw", "L", bpl, 1)
        mask = g.point(lambda v: 255 if v > thr else 0)
        bb = mask.getbbox()                      # 右/下为开区间
        if bb is None:
            return None
        n = mask.histogram()[255]
        return (bb[0], bb[1], bb[2] - 1, bb[3] - 1, n)
    # ---- 慢路径（无 PIL）：只跑小尺寸也不至于卡死，但会明显慢 ----
    x0, y0, x1, y1, n = w, h, -1, -1, 0
    step = 1 if w * h <= 4_000_000 else 3
    for y in range(0, h, step):
        base = y * w
        for x in range(0, w, step):
            s = raw[base + x]                    # Grayscale8：1 字节 1 像素
            if s > thr:
                n += 1
                if x < x0: x0 = x
                if y < y0: y0 = y
                if x > x1: x1 = x
                if y > y1: y1 = y
    if n == 0:
        return None
    k = step
    return (x0, y0, x1 + k - 1, y1 + k - 1, n)


def inter(a, b):
    if not a or not b:
        return 0
    return (max(0, min(a[2], b[2]) - max(a[0], b[0]) + 1)
            * max(0, min(a[3], b[3]) - max(a[1], b[1]) + 1))


def fmt(b):
    return "-" if not b else "%d,%d-%d,%d" % b[:4]


# ---------------------------------------------------------------- 造样本

def make(style, w, h, t, mutate=None):
    sv = L.AmbientSaver(ov)
    sv.ov.saver_style = style
    sv.resize(w, h)
    sv._t0 = time.monotonic() - t
    sv._p_t0 = time.monotonic() - t
    random.seed(20260918)
    sv._particles = None
    sv._p_geom = None
    sv._timer.stop()
    if mutate is not None:
        mutate(sv, w, h)
    return sv


ANIM_METHODS = ("_draw_particle_glow", "_draw_particles", "_draw_bars", "_draw_orbits")


def render_variant(sv, w, h, mode):
    """mode: full / anim（只动画） / text（只文字）"""
    saved = {}
    if mode == "text":
        for m in ANIM_METHODS:
            saved[m] = getattr(sv, m)
            setattr(sv, m, lambda *a, **k: None)
    elif mode == "anim":
        saved["_draw_text_block"] = sv._draw_text_block
        sv._draw_text_block = lambda *a, **k: None
    pm = QPixmap(w, h)
    pm.fill(Qt.black)
    sv.render(pm)
    for k, v in saved.items():
        setattr(sv, k, v)
    return pm


# ---------------------------------------------------------------- 断言（可复用）

def check_layout(plan, w, h, sv):
    """版式层断言，返回问题列表"""
    bad = []
    band, blk = plan["band"], plan["block"]
    if band is not None:
        ia = inter((band.x(), band.y(), band.right(), band.bottom()),
                   (blk.x(), blk.y(), blk.right(), blk.bottom()))
        if ia:
            bad.append("块∩带=%dpx²" % ia)
    sx, sy = w * sv.SAFE_X, h * sv.SAFE_Y
    if blk.left() < sx - 0.5 or blk.right() > w - sx + 0.5:
        bad.append("横向出界 %.1f..%.1f (安全 %.1f..%.1f)"
                   % (blk.left(), blk.right(), sx, w - sx))
    if blk.top() < sy - 0.5 or blk.bottom() > h - sy + 0.5:
        bad.append("纵向出界 %.1f..%.1f (安全 %.1f..%.1f)"
                   % (blk.top(), blk.bottom(), sy, h - sy))
    prev_bot, prev_key = None, None
    for ln in plan["lines"]:
        top = ln["baseline"] - ln["fm"].ascent()
        bot = top + ln["fm"].height()
        if prev_bot is not None and top < prev_bot - 0.5:
            bad.append("行压字 %s→%s (%.1f < %.1f)" % (prev_key, ln["key"], top, prev_bot))
        prev_bot, prev_key = bot, ln["key"]
    if not plan["lines"]:
        bad.append("一行都没有")
    # ④ AOD 换位必须真的有行程 —— 曾经这里是个盲点：4 行版式把文字区填满，
    #    block_h ≈ tz_h，换位代码在跑却一点位移都没有，防烧屏悄悄失效。
    tzh = plan["tz"].height()
    if plan["lines"] and tzh > 0 and plan["travel"] < tzh * 0.05:
        bad.append("换位行程≈0（%.2fpx / 文字区 %.0fpx）—— AOD 换位等于没跑"
                   % (plan["travel"], tzh))
    return bad


fails = []
infos = []
stat = {"cases": 0, "pix": 0, "t": 0.0}
T0 = time.time()


def hdr(title):
    print("=" * 100)
    print(title)
    print("=" * 100)


# ================================================================ A. 版式层

hdr("A. 版式层（直接读 _plan() 的几何）")
print("覆盖两种行数配置：「带歌词」（clock/date/lyric/next 四行）与「仅时钟」（clock/date 两行）")
print("%-9s %-11s %-6s %-8s %-24s %-24s %-9s %s" %
      ("风格", "分辨率", "行", "t(s)", "动画带", "文字块", "行程", "判定"))
print("-" * 116)

for style in STYLES:
    for (w, h) in SIZES:
        for (cur, nxt, scene) in ((NORMAL[0], NORMAL[1], "4行"),
                                  ("", "", "2行")):
            for t in TS:
                # 注释：`ov.song = {...}` **不会**填充 _current_text，
                # 所以这里必须显式赋值，否则整层都在测"无歌词"版式（曾经就是这样漏的）。
                ov._current_text, ov._next_text = cur, nxt
                sv = make(style, w, h, t)
                plan = sv._plan(w, h, t)
                stat["cases"] += 1
                bad = check_layout(plan, w, h, sv)
                if bad:
                    fails.append(("A", style, w, h, t,
                                  "[%s] %s" % (scene, "; ".join(bad))))
                # 换位行程没到设计目标（TRAVEL_MIN）但还不算失效 —— 提示，不判失败
                tzh = plan["tz"].height()
                if tzh > 0 and plan["travel"] < tzh * sv.TRAVEL_MIN - 0.5:
                    infos.append("%s %dx%d [%s] 换位行程 %.0fpx < 目标 %.0fpx（字号已被 K_MIN 卡住）"
                                 % (style, w, h, scene, plan["travel"], tzh * sv.TRAVEL_MIN))
                if (cur and (w, h) == PANEL_SIZE
                        and not any(l["key"] == "lyric" for l in plan["lines"])):
                    infos.append("%s 面板预览 %dx%d [%s] 有歌词却丢了歌词行，只有 %s"
                                 % (style, w, h, scene, [l["key"] for l in plan["lines"]]))
                if (w, h) == (1920, 1080) and scene == "4行":
                    pl = plan
                    fb = "-" if pl["band"] is None else "%.0f,%.0f-%.0f,%.0f" % (
                        pl["band"].x(), pl["band"].y(), pl["band"].right(), pl["band"].bottom())
                    blk = pl["block"]
                    print("%-9s %-11s %-6s %-8.0f %-24s %-24s %-9s %s" %
                          (style, "%dx%d" % (w, h), scene, t, fb,
                           "%.0f,%.0f-%.0f,%.0f" % (blk.x(), blk.y(), blk.right(), blk.bottom()),
                           "%.0fpx" % pl["travel"],
                           ("!! " + "; ".join(bad)) if bad else "ok"))
                elif (w, h) == (1920, 1080):
                    print("%-9s %-11s %-6s %-8.0f %-24s %-24s %-9s %s" %
                          (style, "%dx%d" % (w, h), scene, t,
                           "-" if plan["band"] is None else "%.0f,%.0f" % (
                               plan["band"].top(), plan["band"].bottom()),
                           "%.0f,%.0f" % (plan["block"].top(), plan["block"].bottom()),
                           "%.0fpx" % plan["travel"],
                           ("!! " + "; ".join(bad)) if bad else "ok"))
                sv.deleteLater()

ov._current_text, ov._next_text = NORMAL

# ================================================================ B. 像素层

hdr("B. 像素层（分开渲染动画层 / 文字层，比较亮像素包围盒）")
print("PIL 加速：%s   尺寸表：%s" % ("有（快路径）" if _HAS_PIL else "无（慢路径，已裁尺寸）",
                                    ", ".join("%dx%d" % s for s in SIZES)))
print("%-9s %-11s %-8s %-6s %-22s %-22s %s" %
      ("风格", "分辨率", "t(s)", "文本", "动画bbox", "文字bbox", "判定"))
print("-" * 100)

for style in STYLES:
    for (w, h) in SIZES:
        for (cur, nxt) in (NORMAL, LONGTEXT):
            tag = "长" if cur is LONGTEXT[0] else "常"
            for t in TS_PIX:
                ov._current_text, ov._next_text = cur, nxt
                sv = make(style, w, h, t)
                tk = time.time()
                an = render_variant(sv, w, h, "anim")
                tx = render_variant(sv, w, h, "text")
                full = render_variant(sv, w, h, "full")
                stat["t"] += time.time() - tk
                ba, bt, bf = bbox(an), bbox(tx), bbox(full)
                stat["pix"] += 1

                bad = []
                ip = inter(ba, bt)
                if ip:
                    bad.append("动画∩文字=%dpx²" % ip)
                if bt is None:
                    bad.append("文字层全黑（一个字都没画出来）")
                if ba is None and style != "minimal":
                    bad.append("动画层全黑（风格 %s 应当有动画）" % style)
                # 合成图右/下边界不应超出两层各自的范围
                if bf and bt:
                    if bf[2] > max(bt[2], ba[2] if ba else 0) + 2:
                        bad.append("合成图右溢出 %d" % bf[2])
                    if bf[3] > max(bt[3], ba[3] if ba else 0) + 2:
                        bad.append("合成图下溢出 %d" % bf[3])
                if bad:
                    fails.append(("B", style, w, h, t,
                                  ("长文本 " if tag == "长" else "") + "; ".join(bad)))
                if (w, h) == (1920, 1080) and t == DWELL2:
                    print("%-9s %-11s %-8.0f %-6s %-22s %-22s %s" %
                          (style, "%dx%d" % (w, h), t, tag, fmt(ba), fmt(bt),
                           ("!! " + "; ".join(bad)) if bad else "ok"))
                    full.save(os.path.join(OUT, "%s_%dx%d_%s.png" % (style, w, h, tag)))
                elif (w, h) == (1920, 1080) and t == DWELL0:
                    print("%-9s %-11s %-8.0f %-6s %-22s %-22s %s" %
                          (style, "%dx%d" % (w, h), t, tag, fmt(ba), fmt(bt),
                           ("!! " + "; ".join(bad)) if bad else "ok"))
                sv.deleteLater()

ov._current_text, ov._next_text = NORMAL

# ================================================================ C. 变异自检
# 一个恒真的断言，和一条通过的断言，输出长得一模一样。
# 所以这里故意注入「必然冲突」的版式，要求 A/B 两层都必须报错。

hdr("C. 探针自检（变异测试：故意注入冲突，断言必须被触发）")

PROBE_STYLE = "particle"
PW, PH = 1280, 960
probe_bad = []

# M1. 把动画带放大到整屏 —— 动画就必然压到文字上（裁剪也跟着失效）。
# 注意必须同时把 bcx/bcy 归到整屏中心：星云/星轨是按 plan 的中心画的，
# 只改 band 的话中心还停在原带的中心，动画并不会真的铺到文字上，
# 这个变异就变成"没注入"了（踩过一次，探针自己报了未触发）。
def mut_band_full(sv, w, h):
    orig = sv._plan

    def patched(w2, h2, t2):
        pl = orig(w2, h2, t2)
        pl["band"] = QRectF(0.0, 0.0, float(w2), float(h2))
        pl["bcx"], pl["bcy"] = w2 / 2.0, h2 / 2.0
        return pl
    sv._plan = patched


# M2. 把文字块推到安全边距之外（横向出界）
def mut_block_out(sv, w, h):
    orig = sv._plan

    def patched(w2, h2, t2):
        pl = orig(w2, h2, t2)
        b = pl["block"]
        pl["block"] = QRectF(-60.0, b.y(), b.width(), b.height())
        return pl
    sv._plan = patched


# M3. 把换位行程压成 0 —— 复刻「4 行版式填满文字区」那个真实存在过的失效
def mut_travel_zero(sv, w, h):
    orig = sv._plan

    def patched(w2, h2, t2):
        pl = orig(w2, h2, t2)
        pl["travel"] = 0.0
        return pl
    sv._plan = patched


# --- M1：版式层应报「块∩带」 ---
sv = make(PROBE_STYLE, PW, PH, DWELL2, mutate=mut_band_full)
bad1a = check_layout(sv._plan(PW, PH, DWELL2), PW, PH, sv)
ok1a = any("块∩带" in s for s in bad1a)
print("M1 版式层  动画带=整屏        -> %-4s %s"
      % ("触发" if ok1a else "未触发", "; ".join(bad1a) or "(无问题)"))
if not ok1a:
    probe_bad.append("M1 版式层：注入整屏动画带后，check_layout 没有报「块∩带」")
sv.deleteLater()

# --- M1：像素层应报「动画∩文字」 ---
ov._current_text, ov._next_text = NORMAL
sv = make(PROBE_STYLE, PW, PH, DWELL2, mutate=mut_band_full)
ba = bbox(render_variant(sv, PW, PH, "anim"))
bt = bbox(render_variant(sv, PW, PH, "text"))
ip = inter(ba, bt)
ok1b = ip > 0
print("M1 像素层  动画带=整屏        -> %-4s 动画=%s 文字=%s 交集=%dpx²"
      % ("触发" if ok1b else "未触发", fmt(ba), fmt(bt), ip))
if not ok1b:
    probe_bad.append("M1 像素层：注入整屏动画带后，两个包围盒仍不相交（探针是恒真的）")
sv.deleteLater()

# --- M2：版式层应报「横向出界」 ---
sv = make(PROBE_STYLE, PW, PH, DWELL2, mutate=mut_block_out)
bad2 = check_layout(sv._plan(PW, PH, DWELL2), PW, PH, sv)
ok2 = any("横向出界" in s for s in bad2)
print("M2 版式层  文字块推到屏外      -> %-4s %s"
      % ("触发" if ok2 else "未触发", "; ".join(bad2) or "(无问题)"))
if not ok2:
    probe_bad.append("M2 版式层：文字块被推出安全边距后，check_layout 没有报「横向出界」")
sv.deleteLater()

# --- 反向自检：正常版式下这些断言必须是「不触发」的（否则就是到处误报） ---
sv = make(PROBE_STYLE, PW, PH, DWELL2)
bad_ok = check_layout(sv._plan(PW, PH, DWELL2), PW, PH, sv)
clean = not bad_ok
print("M0 反向对照 正常版式（不应报警）-> %-4s %s"
      % ("干净" if clean else "误报", "; ".join(bad_ok) or "(无问题)"))
if not clean:
    probe_bad.append("M0 反向对照：正常版式被误判为有问题：%s" % "; ".join(bad_ok))
sv.deleteLater()

# --- M3：换位行程归零，必须报「换位行程≈0」 ---
ov._current_text, ov._next_text = NORMAL
sv = make(PROBE_STYLE, PW, PH, DWELL2, mutate=mut_travel_zero)
bad3 = check_layout(sv._plan(PW, PH, DWELL2), PW, PH, sv)
ok3 = any("换位行程" in s for s in bad3)
print("M3 版式层  换位行程归零      -> %-4s %s"
      % ("触发" if ok3 else "未触发", "; ".join(bad3) or "(无问题)"))
if not ok3:
    probe_bad.append("M3 版式层：换位行程被置 0 后，check_layout 没有报「换位行程≈0」")
sv.deleteLater()

fails.extend(("C", "probe", PW, PH, 0.0, s) for s in probe_bad)

# ================================================================ D. 跨风格一致性
# 四种风格是同一个产品的四套皮肤，切主题时文字尺寸不该跳变。
# 这一节是上一轮打磨后**新发现**的问题：particle/orbits 的动画带占掉上半屏，
# 文字区变小，时钟被压到 135px；bars/minimal 能到 183px —— 差 35%。
# 用 TEXT_MAX_H 统一上限锁住后差距收到 11% 以内（时钟 148~164px），这里守住 15%。
# 剩下这 11% 来自各风格动画带高度不同导致的文字区高度差，属可接受量级。

hdr("D. 跨风格一致性（同一分辨率下，四种风格的时钟画布尺寸不应明显跳变）")
print("%-11s %-42s %-10s %s" % ("分辨率", "各风格时钟字号(px)", "极差", "判定"))
print("-" * 100)

rows_txt = ["clock"]
for (w, h) in SIZES:
    if h < 300:                      # 面板缩略图走紧凑模式，行数本身就不同，另算
        continue
    ov._current_text, ov._next_text = NORMAL
    sizes = {}
    for style in STYLES:
        sv = make(style, w, h, DWELL0)
        plan = sv._plan(w, h, DWELL0)
        cl = [l for l in plan["lines"] if l["key"] == "clock"]
        sizes[style] = cl[0]["font"].pixelSize() if cl else 0
        sv.deleteLater()
    vals = [v for v in sizes.values() if v > 0]
    lo, hi = min(vals), max(vals)
    spread = (hi - lo) / float(max(1, lo))
    bad = spread > 0.15
    if bad:
        fails.append(("D", "-", w, h, 0.0,
                      "跨风格时钟字号极差 %.0f%%（%.0f~%.0fpx）" % (spread * 100, lo, hi)))
    print("%-11s %-42s %-10s %s" %
          ("%dx%d" % (w, h),
           " ".join("%s=%d" % (s, sizes[s]) for s in STYLES),
           "%.0f%%" % (spread * 100),
           ("!! 跳变过大" if bad else "ok")))

# 面板缩略图单独看：紧凑模式下四种风格都应当有 clock + lyric
ov._current_text, ov._next_text = NORMAL
pw, ph = PANEL_SIZE
for style in STYLES:
    sv = make(style, pw, ph, DWELL0)
    plan = sv._plan(pw, ph, DWELL0)
    keys = [l["key"] for l in plan["lines"]]
    bad = "lyric" not in keys
    if bad:
        fails.append(("D", style, pw, ph, 0.0, "面板缩略图缺歌词行，只有 %s" % keys))
    print("面板 %-9s %dx%d  行=%s  %s" % (style, pw, ph, keys, "!! 缺歌词" if bad else "ok"))
    sv.deleteLater()

# ================================================================ 汇总

hdr("汇总")
print("版式层用例 %d 个 / 像素层用例 %d 个（渲染+采样 %.1fs，总 %.1fs）"
      % (stat["cases"], stat["pix"], stat["t"], time.time() - T0))
if infos:
    print()
    print("提示（不算失败，Pass 2 处理）：")
    for s in dict.fromkeys(infos):
        print("   · " + s)
if fails:
    print()
    print("!! 发现 %d 处问题：" % len(fails))
    for row in fails[:60]:
        print("   [%s] %-9s %dx%d t=%.0f  %s" % row)
    if len(fails) > 60:
        print("   … 另有 %d 处" % (len(fails) - 60))
else:
    print()
    print("全部通过：所有风格 × 所有分辨率 × 各换位档位 × 两种行数下，"
          "文字均未被动画遮挡、未被屏幕边缘裁切，换位行程未被字号挤没；"
          "探针自检 4/4 确认断言真的会失败")

ov.hotkeys.unregister()
_cfg_sandbox.restore()
print("done, config restored")
sys.exit(1 if fails else 0)
