# -*- coding: utf-8 -*-
"""官网图片资源生成器：从项目 preview/ 与主程序派生 site/assets/ 下的图。

为什么要有这个脚本而不是直接把 png 拷进去：
  · App 图标要以高分辨率重画（主程序的 make_app_icon 只画了 64px，放大就糊）；
  · 设置面板预览是一张 548x1842 的长条，官网里得裁成合适的比例；
  · 一次性把命名规整好，以后改了 UI 重跑一次脚本即可刷新官网截图。

用法（在项目根目录）：
    python site/tools/make_assets.py
"""
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))          # site/tools
SITE = os.path.dirname(HERE)                               # site
ROOT = os.path.dirname(SITE)                               # 项目根
OUT = os.path.join(SITE, "assets")
PREVIEW = os.path.join(ROOT, "preview")

sys.path.insert(0, ROOT)

import lyrics_overlay as L                                 # noqa: E402
from PySide6.QtWidgets import QApplication                 # noqa: E402
from PySide6.QtCore import Qt, QRectF, QPointF             # noqa: E402
from PySide6.QtGui import (QImage, QPainter, QPainterPath,  # noqa: E402
                           QLinearGradient, QColor, QBrush, QPixmap)

app = QApplication(sys.argv)
os.makedirs(OUT, exist_ok=True)

C1 = QColor(L.DEFAULT_ACCENT1)      # #7dd3fc
C2 = QColor(L.DEFAULT_ACCENT2)      # #c4b5fd
INK = QColor(20, 24, 32)


def draw_note(p: QPainter, size: float, col: QColor, k: float = 0.74):
    """在 size×size 的方框内**居中**画一个矢量八分音符。

    不依赖 ♪ 字符（缺字体的机器上会变方框）；k = 音符占方框的比例，留出安全边距，
    否则符头/符尾会顶到圆角方块的边上。

    注意坐标基准是**方框边长 size**、中心固定在 (size/2, size/2) ——
    早先版本把 size 当成"音符自身尺寸"传进来，结果整个音符偏到了左上角。
    """
    p.save()
    p.translate(size / 2, size / 2)
    u = size * k
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    # 符头：-20° 倾斜的椭圆
    p.save()
    p.translate(-0.10 * u, 0.20 * u)
    p.rotate(-20)
    p.drawEllipse(QPointF(0, 0), 0.18 * u, 0.138 * u)
    p.restore()
    # 符干
    p.drawRoundedRect(QRectF(0.045 * u, -0.30 * u, 0.072 * u, 0.53 * u),
                      0.036 * u, 0.036 * u)
    # 符尾：从符干顶端向右下甩出的一笔
    flag = QPainterPath()
    flag.moveTo(0.10 * u, -0.30 * u)
    flag.cubicTo(0.36 * u, -0.20 * u, 0.35 * u, -0.01 * u, 0.20 * u, 0.02 * u)
    flag.cubicTo(0.30 * u, -0.09 * u, 0.24 * u, -0.19 * u, 0.10 * u, -0.21 * u)
    flag.closeSubpath()
    p.fillPath(flag, col)
    p.restore()


def app_icon(size: int) -> QPixmap:
    """高分辨率重画应用图标：渐变圆角方块 + 深色音符（与主程序同设计）。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    inset = size * 0.0625
    grad = QLinearGradient(inset, inset, size - inset, size - inset)
    grad.setColorAt(0.0, C1)
    grad.setColorAt(1.0, C2)
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
                      size * 0.25, size * 0.25)
    # 顶部一道极淡的高光，和 UI 的「光从上方来」语言一致
    hl = QLinearGradient(0, inset, 0, size * 0.55)
    hl.setColorAt(0.0, QColor(255, 255, 255, 46))
    hl.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(hl))
    p.drawRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset),
                      size * 0.25, size * 0.25)
    draw_note(p, size, INK)
    p.end()
    return pm


def crop(name: str, x: int, y: int, w: int, h: int) -> QImage:
    return QImage(os.path.join(PREVIEW, name)).copy(x, y, w, h)


def save(img, name: str):
    path = os.path.join(OUT, name)
    img.save(path)
    print("  %-26s %d x %d" % (name, img.width(), img.height()))


print("图标：")
for s in (512, 256, 180, 32):
    app_icon(s).save(os.path.join(OUT, "icon-%d.png" % s))
    print("  icon-%d.png" % s)
app_icon(256).save(os.path.join(OUT, "icon.ico"), "ICO")

print("截图：")
# 主视觉：玻璃胶囊样式（深色桌面底，最像 macOS 暗色桌面）
save(QImage(os.path.join(PREVIEW, "style_glass_dark.png")), "hero.png")

# 五种样式（深色桌面底）
for key, out in (("native", "style-native.png"), ("glass", "style-glass.png"),
                 ("ios", "style-ios.png"), ("vinyl", "style-vinyl.png"),
                 ("spotify", "style-spotify.png")):
    save(crop("style_%s_dark.png" % key, 0, 0,
              QImage(os.path.join(PREVIEW, "style_%s_dark.png" % key)).width(),
              QImage(os.path.join(PREVIEW, "style_%s_dark.png" % key)).height()), out)

# 设置面板：548x1842 的长条，裁到头部 + 前三张卡片，比例更适合网页
save(crop("settings_panel.png", 0, 0, 548, 1060), "panel.png")

# 右键菜单 / 控制条 / 逐字动画 / 四种屏保
save(QImage(os.path.join(PREVIEW, "menu.png")), "menu.png")
save(QImage(os.path.join(PREVIEW, "controls.png")), "controls.png")
# 逐字动画用深底版：官网这一段在深色区块里，浅底版会显得像放错了图
save(QImage(os.path.join(PREVIEW, "anim_fan_dark.png")), "anim-fan.png")
for key, out in (("particle", "saver-particle.png"), ("minimal", "saver-minimal.png"),
                 ("bars", "saver-bars.png"), ("orbits", "saver-orbits.png")):
    save(QImage(os.path.join(PREVIEW, "saver_%s.png" % key)), out)

# 站点图标（favicon 直接复用苹果触屏尺寸）
shutil.copy2(os.path.join(OUT, "icon-32.png"), os.path.join(OUT, "favicon-32.png"))
shutil.copy2(os.path.join(OUT, "icon-180.png"), os.path.join(OUT, "apple-touch-icon.png"))
print("\n完成 →", OUT)
