# -*- coding: utf-8 -*-
"""渲染 5 种样式 + 设置面板的 2x 预览图，输出到 preview/ 目录，便于肉眼检查排版与配色。

为什么不用 QWidget.render()：窗口带 WA_TranslucentBackground + QGraphicsEffect 时
render() 抓不到内容；这里直接调用真实的 _paint_* 绘制函数（忠实复刻 paintEvent 流程）。

用法：
    python preview_render.py
"""
import json
import os
import shutil
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
from PySide6.QtCore import Qt, QPointF                        # noqa: E402
from PySide6.QtGui import (QPixmap, QPainter, QLinearGradient,  # noqa: E402
                           QColor, QBrush, QRadialGradient)

app = QApplication(sys.argv)
L._load_fonts()
ov = L.LyricOverlay(L.MediaWatcher())

# ---- 造一张"专辑封面"（暖橙 → 品红 → 靛蓝），用于验证取色 / 光晕 / 黑胶标签 ----
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
ov.cover_pix = cov
ov._cover_scaled = None
ov._vinyl_pix = None
ov.accent1, ov.accent2 = L.extract_accent(cov)
ov.bg_color = L.pill_bg_color(ov.accent1)

# ---- 示例歌曲 ----
ov.song = {"title": "夜航西飞", "artist": "陈粒", "source": "qq"}
ov.lines = [[0.0, "若你是一阵风"], [2.0, "我愿是那朵云"], [4.0, "一路向北去"],
            [6.0, "追着光的方向"], [8.0, "不问归期"]]
ov.words = {1: [[2.0, 0.6, "我愿是"], [2.6, 0.9, "那朵云"]]}   # 逐字时间轴示例
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
ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
ov.edge_fade = False                      # 预览不加边缘虚化，方便看清边界

PAINTERS = {"native": "_paint_native", "glass": "_paint_glass", "ios": "_paint_ios",
            "vinyl": "_paint_vinyl", "spotify": "_paint_spotify"}


def paint_into(p):
    """忠实复刻 paintEvent 的绘制流程"""
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setRenderHint(QPainter.TextAntialiasing)
    if ov.status != "PLAYING" and not ov.pause_fade:
        p.setOpacity(0.88)
    getattr(ov, PAINTERS[ov.style_mode])(p)
    if ov.edge_fade:
        ov._paint_edge_fade(p)
    if ov._ctrl_t > 0.01:
        ov._paint_controls(p)


OUT = os.path.join(APP_DIR, "preview")
os.makedirs(OUT, exist_ok=True)
S = 2                                        # 2x 输出
desk = QLinearGradient(0, 0, 1100, 600)      # 浅色桌面底（考验对比度）
desk.setColorAt(0.0, QColor("#f2f4f9"))
desk.setColorAt(1.0, QColor("#dbe1ec"))
# 深色桌面底：描边/落影在浅底和深底上的观感差别极大（浅底上深色落影会变成灰雾，
# 深底上又完全看不见），只出一种底很容易把参数调成"只适合这一种壁纸"。
# v2.4.16 加：两版都出，肉眼对照着看。
desk_dark = QLinearGradient(0, 0, 1100, 600)
desk_dark.setColorAt(0.0, QColor("#232a3d"))
desk_dark.setColorAt(1.0, QColor("#0b0d14"))

for style in L.STYLE_NAMES:
    ov.set_style_mode(style)
    ov._glow_ph = 1.15
    ov._relayout_instant()          # 与真实运行同一份几何（含 _layout_size）
    w, h = ov.width(), ov.height()
    ov._vinyl_ang = 26.0

    layer = QPixmap(w * S, h * S)
    layer.fill(Qt.transparent)
    lp = QPainter(layer)
    lp.scale(S, S)
    paint_into(lp)
    lp.end()

    PAD = 20 * S
    canvas = QPixmap(w * S + 2 * PAD, h * S + 2 * PAD)
    cp = QPainter(canvas)
    cp.fillRect(canvas.rect(), QBrush(desk))
    # v2.4.13 起五个主题统一不挂投影特效（详见 lyrics_overlay.THEME_DROP_SHADOW），
    # 所以预览里也不再补剪影阴影，否则预览与实际观感不一致。
    cp.drawPixmap(PAD, PAD, layer)
    cp.end()
    canvas.save(os.path.join(OUT, "style_%s.png" % style))

    canvas_d = QPixmap(w * S + 2 * PAD, h * S + 2 * PAD)
    cpd = QPainter(canvas_d)
    cpd.fillRect(canvas_d.rect(), QBrush(desk_dark))
    cpd.drawPixmap(PAD, PAD, layer)
    cpd.end()
    canvas_d.save(os.path.join(OUT, "style_%s_dark.png" % style))
    print("saved style_%-8s %d x %d (浅底 + 深底)" % (style, canvas.width(), canvas.height()))

# ---- 控制条图标（6 格现代矢量图标）----
ov.set_style_mode("native")
ov.status = "PLAYING"
ov._ctrl_t = 1.0
pwc, phc = ov.width(), ov.height()
ct = QPixmap(pwc * S, 64 * S)
ct.fill(Qt.transparent)
cp2 = QPainter(ct)
cp2.scale(S, S)
cp2.setRenderHint(QPainter.Antialiasing)
ctrl_r = ov._ctrl_rect()
cp2.save()
cp2.translate(6, 14 - ctrl_r.top())           # 只留控制条区域
ov._paint_controls(cp2)
cp2.restore()
cp2.end()
canvas2 = QPixmap(ct.width() + 24 * S, ct.height() + 24 * S)
c2p = QPainter(canvas2)
c2p.fillRect(canvas2.rect(), QColor("#f2f4f9"))
c2p.drawPixmap(12 * S, 12 * S, ct)
c2p.end()
canvas2.save(os.path.join(OUT, "controls.png"))
print("saved controls        %d x %d" % (canvas2.width(), canvas2.height()))

# ---- 悬停避让对照（v2.4.19）：上=平时，下=悬停（胶囊落在自己预留的一行里，不再压歌词）----
ov.set_style_mode("vinyl")
ov._glow_ph = 1.15
ov._vinyl_ang = 26.0
PADH = 20 * S
shots = []
for _hover in (False, True):
    ov._hovered = _hover
    ov._ctrl_t = 1.0 if _hover else 0.0
    ov._relayout_instant()
    _w, _h = ov.width(), ov.height()
    _layer = QPixmap(_w * S, _h * S)
    _layer.fill(Qt.transparent)
    _lp = QPainter(_layer)
    _lp.scale(S, S)
    paint_into(_lp)
    _lp.end()
    shots.append(_layer)
ov._hovered = False
ov._ctrl_t = 0.0

_gap = 18 * S
cv = QPixmap(max(shots[0].width(), shots[1].width()) + 2 * PADH,
             shots[0].height() + _gap + shots[1].height() + 2 * PADH)
_cvp = QPainter(cv)
_cvp.fillRect(cv.rect(), QBrush(desk))
_cvp.drawPixmap(PADH, PADH, shots[0])
_cvp.drawPixmap(PADH, PADH + shots[0].height() + _gap, shots[1])
_cvp.end()
cv.save(os.path.join(OUT, "hover_avoid.png"))
print("saved hover_avoid      %d x %d (悬停前后对照)" % (cv.width(), cv.height()))

# ---- 扇形逐字动画（逐字动画里最花哨的一种）----
ov.set_style_mode("native")
ov.set_anim_style("fan")
ov._current_text = "追着光的方向一路向北"
ov._next_text = "不问归期"
ov.lines = [[0.0, ov._current_text], [3.0, ov._next_text]]
ov.cur_idx = 0
ov.words = {}
ov._spans_cache.clear()
ov._line_t = 1.0
ov.anchor_pos = 1.6
ov.anchor_ts = time.monotonic()
ov._relayout_instant()
w, h = ov.width(), ov.height()
layer = QPixmap(w * S, h * S)
layer.fill(Qt.transparent)
lp = QPainter(layer)
lp.scale(S, S)
paint_into(lp)
lp.end()
PAD = 20 * S
canvas3 = QPixmap(w * S + 2 * PAD, h * S + 2 * PAD)
cp3 = QPainter(canvas3)
cp3.fillRect(canvas3.rect(), QBrush(desk))
cp3.drawPixmap(PAD, PAD, layer)
cp3.end()
canvas3.save(os.path.join(OUT, "anim_fan.png"))
print("saved anim_fan        %d x %d (浅底)" % (canvas3.width(), canvas3.height()))

# 同一张动画也出一版深底：官网把“逐字动画”这一段放在深色区块里，
# 只有浅底版会和旁边清一色的深底截图打架（看起来像放错了一张图）。
canvas3d = QPixmap(w * S + 2 * PAD, h * S + 2 * PAD)
cp3d = QPainter(canvas3d)
cp3d.fillRect(canvas3d.rect(), QBrush(desk_dark))
cp3d.drawPixmap(PAD, PAD, layer)
cp3d.end()
canvas3d.save(os.path.join(OUT, "anim_fan_dark.png"))
print("saved anim_fan_dark   %d x %d (深底)" % (canvas3d.width(), canvas3d.height()))

# ---- 氛围屏保：四风格（粒子 / 极简 / 音浪 / 星轨）----
ov.lines = [[0.0, "夜色温柔"], [3.0, "风也温柔"]]
ov._current_text, ov._next_text = "夜色温柔", "风也温柔"
ov.cur_idx = 0
for sv_style, sv_name in (("particle", "saver_particle"),
                          ("minimal", "saver_minimal"),
                          ("bars", "saver_bars"),
                          ("orbits", "saver_orbits")):
    ov.saver_style = sv_style
    sv = L.AmbientSaver(ov)
    sv.resize(960, 540)
    sv._t0 = time.monotonic() - 21.0          # 取一个漂移中的时刻
    svpm = QPixmap(960, 540)
    svpm.fill(Qt.black)
    sv.render(svpm)
    svpm.save(os.path.join(OUT, "%s.png" % sv_name))
    print("saved %-15s 960 x 540 (%s)" % (sv_name, sv_style))

# ---- 设置面板（抓完整内容，不只看视口）----
ov._open_panel()
pn = ov.panel
pn.setGraphicsEffect(None)                   # 面板自带淡入用的透明度特效，抓图前去掉
pn.ensurePolished()
# 面板带滚动区，抓图时把窗口撑到内容全高，一次拍全（否则只能看到首屏）
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
bg.save(os.path.join(OUT, "settings_panel.png"))
print("saved settings_panel  %d x %d" % (bg.width(), bg.height()))

# ---- 菜单（托盘菜单与右键菜单共用 menu_qss 这套皮肤）----
# 右键菜单曾经漏套皮肤、弹出的是系统原生白底菜单，所以这里也出一张预览，
# 让"菜单有没有变白"能一眼看出来。托盘菜单需要 QSystemTrayIcon，这里直接抓
# 右键菜单（两者用的 `menu_qss` 是同一个函数）。
try:
    ov.set_style_mode("glass")
    cm = ov._build_context_menu()
    cm.adjustSize()
    cm.show()
    app.processEvents()
    mg = cm.grab()
    cm.hide()

    # 找一个含可勾选项的子菜单（样式/摆放位置），单独抓出来看勾选标记与右侧箭头
    sub = None
    for act in cm.actions():
        m = act.menu()
        if m is not None and any(x.isCheckable() for x in m.actions()):
            sub = m
            break
    sg = None
    if sub is not None:
        sub.adjustSize()
        sub.show()
        app.processEvents()
        sg = sub.grab()
        sub.hide()

    pad = 22
    cols = [p for p in (mg, sg) if p is not None]
    W = sum(p.width() for p in cols) + pad * (len(cols) + 1)
    H = max(p.height() for p in cols) + pad * 2
    canvas = QPixmap(W, H)
    mp = QPainter(canvas)
    mp.fillRect(canvas.rect(), QBrush(desk))          # 浅底：深色菜单的圆角与描边才看得清
    x = pad
    for p in cols:
        mp.drawPixmap(x, pad, p)
        x += p.width() + pad
    mp.end()
    canvas.save(os.path.join(OUT, "menu.png"))
    print("saved menu            %d x %d (主菜单 + 子菜单)" % (canvas.width(), canvas.height()))
except Exception as exc:                                # 菜单抓不到不该拖垮整个预览
    print("menu preview 跳过：%s" % exc)

# ---- 对话框（关于 / 接管警告）----
# 曾经用 QMessageBox.about() / .warning() 的静态方法：那是系统原生白底弹窗，
# 不继承任何皮肤，和整套深色 UI 打架。这里抓一张自制对话框的预览印证。
try:
    box = L.build_message_box(None, "关于 桌面歌词",
                              "桌面歌词 v%s" % L.APP_VERSION,
                              "本地运行，不上传任何数据。\n歌词来自公开接口，仅供个人学习使用。",
                              accent=ov.accent1)
    box.show()
    app.processEvents()
    dg = box.grab()
    box.hide()
    dcanvas = QPixmap(dg.width() + 44, dg.height() + 44)
    dp = QPainter(dcanvas)
    dp.fillRect(dcanvas.rect(), QBrush(desk))
    dp.drawPixmap(22, 22, dg)
    dp.end()
    dcanvas.save(os.path.join(OUT, "dialog.png"))
    print("saved dialog          %d x %d" % (dcanvas.width(), dcanvas.height()))
except Exception as exc:
    print("dialog preview 跳过：%s" % exc)

ov.hotkeys.unregister()
_cfg_sandbox.restore()
print("done, config restored")
