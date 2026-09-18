# -*- coding: utf-8 -*-
"""把关键 UI 区域放大 2x 拼成一张巡检图，供人眼判断质感（卡片/按钮/控件/控制条）。

用法：python _diag_ui_zoom.py   → 输出 preview/ui_zoom.png
面板预览高且窄，直接看整张会糊成一团；这里裁出头部、卡片、控件区分别放大再拼。
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QImage, QPainter, QPixmap, QColor
from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)

OUT = "preview"
Z = 2

def crop(path, x, y, w, h, z=Z):
    im = QImage(os.path.join(OUT, path))
    return QPixmap.fromImage(im.copy(x, y, w, h)).scaled(
        w * z, h * z, Qt.KeepAspectRatio, Qt.FastTransformation)

# 面板：头部 + 第一张卡（同步）+ 一个卡片标题
p1 = crop("settings_panel.png", 0, 0, 548, 120)
p2 = crop("settings_panel.png", 0, 118, 548, 230)
p3 = crop("settings_panel.png", 0, 380, 548, 250)
p4 = crop("controls.png", 0, 0, 840, 176, 2)

cols = [p1, p2, p3]
W = max(p.width() for p in cols) + 40
H = sum(p.height() for p in cols) + 40 + p4.height()
canvas = QPixmap(W, H)
pt = QPainter(canvas)
pt.fillRect(canvas.rect(), QColor("#e9edf5"))
y = 20
for p in cols:
    pt.drawPixmap(20, y, p)
    y += p.height() + 20
pt.drawPixmap(20, y, p4)
pt.setPen(QColor("#8892a6"))
pt.end()
canvas.save(os.path.join(OUT, "ui_zoom.png"))
print("saved ui_zoom.png", canvas.width(), canvas.height())
