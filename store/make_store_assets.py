# -*- coding: utf-8 -*-
"""生成 Microsoft Store / MSIX 需要的全套图标资产（从项目根的 icon.png 派生）。

用 QImage + QPainter 离屏渲染，不弹窗、不需要显示器，也不依赖 PIL：
跑任何 Qt 绘制前设 QT_QPA_PLATFORM=offscreen 即可（本项目惯例）。

清单（MSIX VisualElements / DefaultTile 引用到的全部尺寸）：
  列表与商店：StoreLogo 50 + scale-200(100)
              Square44x44 44 + scale-200(88) + targetsize 16~256 一档
  磁贴：      Square71x71(71) Square150x150(150)+scale-200(300)
              Square310x310(310) Wide310x150(310x150)+scale-200(620x300)

磁贴类带品牌底色（#14171F，与应用暗色主题一致）；
列表/商店类保持透明底（图标本身带圆角方形轮廓，直接用）。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(BASE, "..", "icon.png")
OUT = os.path.join(BASE, "assets")          # 生成物落在 store/assets/，构建时拷进布局

BRAND_BG = QColor("#14171F")
TRANSPARENT = QColor(0, 0, 0, 0)

# (文件名, 宽, 高, 底色None=透明, 图标占比)
_TILES = [
    ("StoreLogo.png",              50,  50, None,          0.92),
    ("StoreLogo.scale-200.png",   100, 100, None,          0.92),
    ("Square44x44Logo.png",        44,  44, None,          0.92),
    ("Square44x44Logo.scale-200.png", 88, 88, None,       0.92),
    ("Square71x71Logo.png",        71,  71, BRAND_BG,      0.66),
    ("Square150x150Logo.png",     150, 150, BRAND_BG,      0.62),
    ("Square150x150Logo.scale-200.png", 300, 300, BRAND_BG, 0.62),
    ("Square310x310Logo.png",     310, 310, BRAND_BG,      0.60),
    ("Wide310x150Logo.png",       310, 150, BRAND_BG,      0.74),
    ("Wide310x150Logo.scale-200.png", 620, 300, BRAND_BG,  0.74),
]

# Square44 的 targetsize 一档（应用列表/任务栏在不同 DPI 下取用）
_TARGETS = [16, 20, 24, 30, 36, 40, 48, 60, 64, 72, 80, 96, 256]


def render(src: str, w: int, h: int, bg, ratio: float) -> QImage:
    """把 icon.png 等比居中画到 w×h 画布：磁贴带底色，列表图标保持透明。"""
    icon = QImage(src)
    if icon.isNull():
        raise SystemExit("读不了图标源文件：%s" % src)
    canvas = QImage(w, h, QImage.Format_ARGB32)
    canvas.fill(bg if bg is not None else TRANSPARENT)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    side = int(min(w, h) * ratio)
    scaled = icon.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x, y = (w - scaled.width()) // 2, (h - scaled.height()) // 2
    p.drawImage(x, y, scaled)
    p.end()
    return canvas


def generate(out_dir: str = OUT, src: str = ICON) -> list:
    """生成全部资产，返回写入的文件列表。"""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, w, h, bg, ratio in _TILES:
        path = os.path.join(out_dir, name)
        render(src, w, h, bg, ratio).save(path)
        written.append(path)
    for t in _TARGETS:
        path = os.path.join(out_dir, "Square44x44Logo.targetsize-%d.png" % t)
        render(src, t, t, None, 0.92).save(path)
        written.append(path)
    return written


def verify(out_dir: str = OUT) -> bool:
    """检查资产齐全且尺寸正确（构建前的门禁）。"""
    import struct

    def png_size(path):
        with open(path, "rb") as f:
            head = f.read(33)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return w, h

    need = {name: (w, h) for name, w, h, _b, _r in _TILES}
    for t in _TARGETS:
        need["Square44x44Logo.targetsize-%d.png" % t] = (t, t)
    ok = True
    for name, size in sorted(need.items()):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            print("  缺失: %s" % name)
            ok = False
            continue
        real = png_size(path)
        if real != size:
            print("  尺寸不对: %s 期望 %s 实际 %s" % (name, size, real))
            ok = False
    return ok


if __name__ == "__main__":
    files = generate()
    print("生成 %d 个资产 → %s" % (len(files), OUT))
    print("校验：", "全部通过" if verify() else "有问题，见上")
