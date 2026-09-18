# -*- coding: utf-8 -*-
"""描边 A/B 对照：把「旧版实心粗描边」与「新版双层柔和描边」在同一场景下并排渲染。

为什么要单独做这个脚本：只看一种桌面底色的预览图时，参数很容易被调成「只适合这一种
壁纸」。v2.4.16 第一版就踩过这个坑——柔和阴影在**浅色**壁纸上会摊成一片灰雾，而单看
深色壁纸觉得完美。所以这里固定输出 2 行 × 2 列：

            浅色桌面        深色桌面
    旧版     ....            ....
    新版     ....            ....

「旧版」是**忠实复刻**，不只是把 QPen 换回单层：当年各样式实际传的宽度常量
（HALO 5.0 / 4.2、DIM 96 / 100）也一并还原，否则对照不公平。

用法：
    python _diag_halo_ab.py                 # 输出 native / glass / vinyl 三套
    python _diag_halo_ab.py native vinyl    # 只出指定样式
输出：preview/halo_ab_<style>.png
不写用户配置，跑完自动还原。
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
BAK = CFG + ".abbak"
_had_cfg = os.path.exists(CFG)
if _had_cfg:
    shutil.copy2(CFG, BAK)
os.makedirs(os.path.dirname(CFG), exist_ok=True)
with open(CFG, "w", encoding="utf-8") as f:
    json.dump({"hotkeys": False, "keepalive": False, "idle_saver": False,
               "show_trans": True, "glow": True,
               "show_time": True, "font_scale": 1.0}, f)

import lyrics_overlay as L                                     # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402
from PySide6.QtCore import Qt, QPointF                         # noqa: E402
from PySide6.QtGui import (QPixmap, QPainter, QLinearGradient,   # noqa: E402
                           QColor, QBrush, QRadialGradient, QPen, QFont)

app = QApplication(sys.argv)
L._load_fonts()

# ---- 封面（用渐变合成一张，和 preview_render.py 保持一致）----
cov = QPixmap(500, 500)
_p = QPainter(cov)
_g = QLinearGradient(0, 0, 500, 500)
_g.setColorAt(0.0, QColor("#ff8a3d"))
_g.setColorAt(0.45, QColor("#e0407a"))
_g.setColorAt(1.0, QColor("#4a3aff"))
_p.fillRect(0, 0, 500, 500, QBrush(_g))
_rg = QRadialGradient(QPointF(150, 130), 280)
_rg.setColorAt(0.0, QColor(255, 255, 255, 130))
_rg.setColorAt(1.0, QColor(255, 255, 255, 0))
_p.setPen(Qt.NoPen)
_p.setBrush(QBrush(_rg))
_p.drawEllipse(QPointF(150, 130), 280, 280)
_p.end()

ov = L.LyricOverlay(L.MediaWatcher())            # 只借用绘制逻辑，不启动 watcher/计时器
ov.cover_pix = cov
ov._cover_scaled = None
ov._vinyl_pix = None
ov.accent1, ov.accent2 = L.extract_accent(cov)
ov.bg_color = L.pill_bg_color(ov.accent1)

# ---- 示例歌曲：故意用长短不一的歌词，既能看唱到的字也能看没唱到的 ----
ov.song = {"title": "夜航西飞", "artist": "陈粒", "source": "qq"}
ov.lines = [[0.0, "若你是一阵风"], [2.0, "我愿是那朵云"], [4.0, "一路向北去"],
            [6.0, "追着光的方向"], [8.0, "不问归期"]]
ov.words = {1: [[2.0, 0.6, "我愿是"], [2.6, 0.9, "那朵云"]]}
ov.trans = [[2.0, "If you were the wind"]]
ov._trans_map = ov._build_trans_map()
ov.duration = 254.0
ov.status = "PLAYING"
ov._current_text = ov.lines[1][1]
ov._next_text = ov.lines[2][1]
ov.cur_idx = 1
ov._line_t = 1.0
ov.anchor_pos = 2.65          # 停在"我愿是"唱完、"那朵云"还没唱的瞬间
ov.anchor_ts = time.monotonic()
ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
ov.edge_fade = False

PAINTERS = {"native": "_paint_native", "glass": "_paint_glass", "ios": "_paint_ios",
            "vinyl": "_paint_vinyl", "spotify": "_paint_spotify"}

# ---- 旧版参数（v2.4.15 及以前的实际取值）----
OLD_BARE, OLD_CARD = 5.0, 4.2
OLD_DIM_BARE, OLD_DIM_CARD = 96, 100
OLD_PEN_ALPHA = 170
NEW_PENS = L.LyricOverlay._halo_pens


def use_old():
    L.HALO_BARE, L.HALO_CARD = OLD_BARE, OLD_CARD
    L.DIM_BARE, L.DIM_CARD = OLD_DIM_BARE, OLD_DIM_CARD
    L.LyricOverlay._halo_pens = _old_pens


def use_new():
    # 这些常量在模块被 import 时已经读进函数体做全局查找，所以这里直接改模块属性即可
    L.HALO_BARE = _NEW_VALS["bare"]
    L.HALO_CARD = _NEW_VALS["card"]
    L.DIM_BARE = _NEW_VALS["dim_bare"]
    L.DIM_CARD = _NEW_VALS["dim_card"]
    L.LyricOverlay._halo_pens = NEW_PENS


def _old_pens(self, w):
    """v2.4.15 的实现：单层实心黑描边"""
    if w <= 0:
        return ()
    return (QPen(QColor(0, 0, 0, OLD_PEN_ALPHA), w, Qt.SolidLine,
                 Qt.RoundCap, Qt.RoundJoin),)


# 记录新版真实取值，供 use_new 还原
_NEW_VALS = {"bare": L.HALO_BARE, "card": L.HALO_CARD,
             "dim_bare": L.DIM_BARE, "dim_card": L.DIM_CARD}

DESK_L = QLinearGradient(0, 0, 1100, 600)
DESK_L.setColorAt(0.0, QColor("#f2f4f9"))
DESK_L.setColorAt(1.0, QColor("#dbe1ec"))
DESK_D = QLinearGradient(0, 0, 1100, 600)
DESK_D.setColorAt(0.0, QColor("#232a3d"))
DESK_D.setColorAt(1.0, QColor("#0b0d14"))

S = 2
PAD = 18 * S
LBL = 26 * S          # 左侧标签列宽


def paint_into(p):
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.TextAntialiasing)
    getattr(ov, PAINTERS[ov.style_mode])(p)


def render_layer(style):
    ov.set_style_mode(style)
    ov._glow_ph = 1.15
    ov._vinyl_ang = 26.0
    pw, ph = ov._pill_size()
    m = ov._margin()
    w, h = int(pw + 2 * m), int(ph + 2 * m)
    ov.resize(w, h)
    pm = QPixmap(w * S, h * S)
    pm.fill(Qt.transparent)
    lp = QPainter(pm)
    lp.scale(S, S)
    paint_into(lp)
    lp.end()
    return pm, w, h


def make_sheet(style):
    use_old()
    old_pm, w, h = render_layer(style)
    use_new()
    new_pm, w2, h2 = render_layer(style)

    cw, ch = w * S + 2 * PAD, h * S + 2 * PAD
    sheet = QPixmap(LBL + 2 * cw, 2 * ch)
    sheet.fill(QColor("#14161c"))
    sp = QPainter(sheet)
    sp.setRenderHint(QPainter.Antialiasing)
    sp.setRenderHint(QPainter.TextAntialiasing)

    font = QFont("Microsoft YaHei UI", 10 * S // 2)
    font.setBold(True)
    sp.setFont(font)

    rows = [("旧版  实心粗描边", old_pm), ("新版  双层柔和描边", new_pm)]
    cols = [("浅色桌面", DESK_L), ("深色桌面", DESK_D)]
    for r, (rlabel, pm) in enumerate(rows):
        for c, (clabel, desk) in enumerate(cols):
            x0, y0 = LBL + c * cw, r * ch
            sp.fillRect(x0, y0, cw, ch, QBrush(desk))
            sp.drawPixmap(x0 + PAD, y0 + PAD, pm)
            # 列标题（只在第一行画）
            if r == 0:
                sp.setPen(QColor(150, 158, 172))
                sp.drawText(x0 + PAD, y0 + 13 * S, clabel)
            sp.setPen(QColor(120, 128, 142))
            sp.drawText(x0 + PAD, y0 + ch - 7 * S, clabel)
        # 行标签（竖排太麻烦，横排画在左列顶部）
        sp.setPen(QColor(226, 232, 244) if r == 0 else QColor(255, 122, 168))
        sp.drawText(6 * S, r * ch + 20 * S, rlabel)

    sp.end()
    out = os.path.join(APP_DIR, "preview", "halo_ab_%s.png" % style)
    sheet.save(out)
    print("saved %-34s %d x %d" % (os.path.basename(out), sheet.width(), sheet.height()))


targets = [a for a in sys.argv[1:] if a in PAINTERS] or ["native", "glass", "vinyl"]
for st in targets:
    make_sheet(st)

# ---- 还原用户配置 ----
try:
    if _had_cfg:
        shutil.copy2(BAK, CFG)
        os.remove(BAK)
    else:
        os.remove(CFG)
except OSError:
    pass
print("\n提示：两行分别对应旧/新描边，两列分别是浅色与深色桌面。")
