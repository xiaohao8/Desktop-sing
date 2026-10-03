# -*- coding: utf-8 -*-
"""2.0 配色主题验证：固定主题贯穿 5 种悬浮样式 + ThemeSwatches 色板 + 设置面板。

复用 preview_render.py 的离屏渲染思路（直接调真实 _paint_* 绘制函数），
输出到 preview/theme20_*.png，供肉眼检查换肤是否全链路生效。
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import _cfg_sandbox                                           # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False,
                   show_trans=True, glow=True, show_time=True, font_scale=1.0)

import lyrics_overlay as L                                    # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402
from PySide6.QtCore import Qt                                 # noqa: E402
from PySide6.QtGui import (QPixmap, QPainter, QLinearGradient,  # noqa: E402
                           QColor, QBrush)

app = QApplication(sys.argv)
L._load_fonts()
ov = L.LyricOverlay(L.MediaWatcher())

# ---- 示例歌曲（不给封面：验证固定主题不依赖封面取色）----
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
ov.anchor_pos = 2.65
ov.anchor_ts = time.monotonic()
ov.edge_fade = False

PAINTERS = {"native": "_paint_native", "glass": "_paint_glass", "ios": "_paint_ios",
            "vinyl": "_paint_vinyl", "spotify": "_paint_spotify"}
OUT = os.path.join(APP_DIR, "preview")
S = 2
desk = QLinearGradient(0, 0, 1100, 600)
desk.setColorAt(0.0, QColor("#f2f4f9"))
desk.setColorAt(1.0, QColor("#dbe1ec"))
desk_dark = QLinearGradient(0, 0, 1100, 600)
desk_dark.setColorAt(0.0, QColor("#232a3d"))
desk_dark.setColorAt(1.0, QColor("#0b0d14"))


def paint_into(p):
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.TextAntialiasing)
    getattr(ov, PAINTERS[ov.style_mode])(p)


def render_style_pair(tag):
    ov._glow_ph = 1.15
    ov._relayout_instant()
    w, h = ov.width(), ov.height()
    ov._vinyl_ang = 26.0
    layer = QPixmap(w * S, h * S)
    layer.fill(Qt.transparent)
    lp = QPainter(layer)
    lp.scale(S, S)
    paint_into(lp)
    lp.end()
    for bg, name in ((desk, "theme20_%s.png" % tag),
                     (desk_dark, "theme20_%s_dark.png" % tag)):
        PAD = 20 * S
        canvas = QPixmap(w * S + 2 * PAD, h * S + 2 * PAD)
        cp = QPainter(canvas)
        cp.fillRect(canvas.rect(), QBrush(bg))
        cp.drawPixmap(PAD, PAD, layer)
        cp.end()
        canvas.save(os.path.join(OUT, name))
    print("saved theme20_%s  (浅底 + 深底)" % tag)


# ---- 1) 固定主题「玫瑰粉」贯穿 5 种样式 ----
ov.apply_color_theme("rose")
assert ov.color_mode == "fixed" and ov.accent1.name().upper() == "#FB7185", \
    "apply_color_theme 未生效: %s %s" % (ov.color_mode, ov.accent1.name())
assert ov.cfg.get("color_theme") == "rose", "配置未持久化"
for style in L.STYLE_NAMES:
    ov.set_style_mode(style)
    render_style_pair("rose_%s" % style)

# ---- 2) 固定主题「琥珀金」抽验两种样式（确认主题间切换）----
ov.apply_color_theme("amber")
ov.set_style_mode("glass")
render_style_pair("amber_glass")
ov.set_style_mode("native")
render_style_pair("amber_native")

# ---- 3) 切回封面取色（无封面 → 应回落默认蓝紫）----
ov.set_color_mode("auto")
assert ov.accent1.name().upper() == L.DEFAULT_ACCENT1.name().upper(), \
    "auto 模式未回落默认色: %s" % ov.accent1.name()
ov.set_style_mode("glass")
render_style_pair("auto_glass")

# ---- 4) ThemeSwatches 色板（fixed 选中 / auto 降透明两态）----
sw_f = L.ThemeSwatches("sakura")
sw_f.grab().save(os.path.join(OUT, "theme20_swatches_fixed.png"))
sw_a = L.ThemeSwatches("sakura")
sw_a.set_mode("auto")
sw_a.grab().save(os.path.join(OUT, "theme20_swatches_auto.png"))
print("saved theme20_swatches_fixed / _auto")

# ---- 5) 设置面板整卡（滚动到配色卡片位置抓全高）----
ov._open_panel()
pn = ov.panel
pn.setGraphicsEffect(None)
pn.ensurePolished()
pn.resize(548, 760)
pn.show()
app.processEvents()
content = getattr(pn, "_content", None)
if content is not None:
    content.adjustSize()
    need = max(content.sizeHint().height(), content.height()) + 8
    pn.resize(548, min(2400, need))
    app.processEvents()
grab = pn.grab()
pn.hide()
bg = QPixmap(grab.size())
bp = QPainter(bg)
bp.fillRect(bg.rect(), QColor("#0f1116"))
bp.drawPixmap(0, 0, grab)
bp.end()
bg.save(os.path.join(OUT, "theme20_settings_panel.png"))
print("saved theme20_settings_panel %d x %d" % (bg.width(), bg.height()))

# ---- 6) 托盘「配色主题」子菜单勾选态 ----
acts = ov._color_actions
auto_on = not ov._color_auto_action.isChecked()
checked = [t for t, a in acts.items() if a.isChecked()]
print("menu sync: auto_checked=%s checked_theme=%s (应为 True/[])" % (auto_on, checked))

print("ALL DONE")
