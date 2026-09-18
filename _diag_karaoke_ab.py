# -*- coding: utf-8 -*-
"""逐字卡拉OK「柔性波前」A/B 对照诊断（旧=整字平色 / 新=沿字宽渐变）。

用法：python _diag_karaoke_ab.py   → 输出 preview/karaoke_ab.png
靠 L.KARAOKE_SOFT_EDGE 开关在同一张图上出上下两版，肉眼直接对照波前方向对不对。
"""
import json
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

CFG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                   "Desktop-sing", "config.json")
BAK = CFG + ".kpbak"
_had = os.path.exists(CFG)
if _had:
    shutil.copy2(CFG, BAK)
os.makedirs(os.path.dirname(CFG), exist_ok=True)
with open(CFG, "w", encoding="utf-8") as f:
    json.dump({"hotkeys": False, "keepalive": False, "idle_saver": False,
               "show_trans": False, "glow": False, "show_time": False}, f)

import lyrics_overlay as L                                       # noqa: E402
from PySide6.QtWidgets import QApplication                        # noqa: E402
from PySide6.QtCore import Qt                                     # noqa: E402
from PySide6.QtGui import QPixmap, QPainter, QColor               # noqa: E402

app = QApplication(sys.argv)
L._load_fonts()
ov = L.LyricOverlay(L.MediaWatcher())
ov.set_style_mode("native")
TEXT = "唱过一段未唱的字"
ov.song = {"title": "测试", "artist": "歌手", "source": "qq", "cover": None}
ov.cover_pix = None
ov.accent1, ov.accent2 = QColor("#ff5c8a"), QColor("#ffa24a")
ov.bg_color = L.pill_bg_color(ov.accent1)
ov.lines = [[0.0, TEXT], [8.0, "下一句"]]
ov.words = {0: [[float(i), 1.0, ch] for i, ch in enumerate(TEXT)]}
ov.trans = []
ov._trans_map = {}
ov.duration = 60.0
ov._current_text = TEXT
ov._next_text = "下一句"
ov.cur_idx = 0
ov.status = "PLAYING"
ov._line_t = 1.0          # 入场动画已结束，避免整行变换干扰观察
ov._ctrl_t = 0.0
ov.edge_fade = False
ov.glow = ov.show_trans = ov.show_time = ov.show_cover = False
POS = 4.5                 # 第 5 个字（下标 4）正好唱到一半 → 波前落在它中间
ov._current_pos = lambda: POS

S = 3
out = []

for edge in (False, True):
    L.KARAOKE_SOFT_EDGE = edge
    pw, ph = ov._pill_size()
    m = ov._margin()
    w, h = int(pw + 2 * m), int(ph + 2 * m)
    ov.resize(w, h)
    layer = QPixmap(w * S, h * S)
    layer.fill(Qt.transparent)
    lp = QPainter(layer)
    lp.scale(S, S)
    lp.setRenderHint(QPainter.Antialiasing)
    lp.setRenderHint(QPainter.TextAntialiasing)
    ov._paint_native(lp)
    lp.end()
    out.append(layer)

# 上下拼：上=旧（平色），下=新（渐变），铺在深色底上
W = out[0].width()
H = sum(p.height() for p in out) + 40
canvas = QPixmap(W + 40, H)
cp = QPainter(canvas)
cp.fillRect(canvas.rect(), QColor("#123a52"))
y = 20
for p in out:
    cp.drawPixmap(20, y, p)
    y += p.height() + 20
cp.end()
canvas.save(os.path.join(APP_DIR, "preview", "karaoke_ab.png"))

L.KARAOKE_SOFT_EDGE = True
if _had:
    shutil.copy2(BAK, CFG)
    os.remove(BAK)
else:
    os.remove(CFG)
ov.hotkeys.unregister()
print("saved karaoke_ab.png", canvas.width(), canvas.height())
