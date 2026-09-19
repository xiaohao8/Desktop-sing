# -*- coding: utf-8 -*-
"""生成 Microsoft Store / MSIX 需要的全套图标资产（从项目根的 icon.png 派生）。

用 QImage + QPainter 离屏渲染，不弹窗、不需要显示器，也不依赖 PIL：
跑任何 Qt 绘制前设 QT_QPA_PLATFORM=offscreen 即可（本项目惯例）。

资产清单依据官方文档「Construct your Windows app's icon」：
  https://learn.microsoft.com/windows/apps/design/style/iconography/app-icon-construction

  ① 商店列表（required）：StoreLogo 50 → scale-100/125/150/200/400
  ② 应用列表（required）：Square44x44Logo 44 → scale-100/200/400
     + targetsize 16~256 全套（Windows 用它画任务栏/右键菜单，避免加底板）
     + altform-unplated 深浅主题变体（缺失时图标会被系统加底板，观感变差）
  ③ 磁贴：Square71(SmallTile) / Square150(MedTile，Win11 发布最低要求)
     / Wide310x150 / Square310x310(LargeTile)，各带 100/125/150/200/400
  ④ 启动屏（可选，桌面桥应用不显示，但补齐防审核提问）：SplashScreen 620x300 → 各档

两套画法（与应用的暗色品牌一致）：
  - 磁贴类：带品牌底色 #14171F，图标留出安全边距（磁贴要被系统裁切）
  - 列表/商店类：透明底，图标本身带圆角方形轮廓，直接用
  - altform-unplated：透明底且不留边距（系统按原始像素贴，不加底板）
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

# 官方缩放档位：100% 是基准，125/150/200/250/300/400 按显示 DPI 取用。
# 文档建议至少 100/200/400；这里把 125/150 也备上，省得系统拉伸。
_SCALES = (100, 125, 150, 200, 400)

# (基准名, 基准宽, 基准高, 底色None=透明, 图标占比)
_BASES = [
    ("StoreLogo",             50,  50, None,      0.92),   # 商店列表（required）
    ("Square44x44Logo",       44,  44, None,      0.92),   # 应用列表 / 任务栏（required）
    ("Square71x71Logo",       71,  71, BRAND_BG,  0.66),   # 小磁贴
    ("Square150x150Logo",    150, 150, BRAND_BG,  0.62),   # 中磁贴（Win11 发布最低要求）
    ("Square310x310Logo",    310, 310, BRAND_BG,  0.60),   # 大磁贴（Win10）
    ("Wide310x150Logo",      310, 150, BRAND_BG,  0.74),   # 宽磁贴（required）
    ("SplashScreen",         620, 300, BRAND_BG,  0.42),   # 启动屏（可选，桌面桥不显示）
]

# Square44 的 targetsize 一档：Windows 用精确像素尺寸画任务栏 / 右键菜单 / 搜索结果
_TARGETS = [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256]


def _scaled(base: int, scale: int) -> int:
    """按缩放档位换算像素尺寸（125% 会有小数，向上取整避免糊）。"""
    return (base * scale + 99) // 100


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


def _plan(bases=None, scales=_SCALES, targets=None):
    """算出要产出的 (文件名, 宽, 高, 底色, 占比) 全表。"""
    bases = _BASES if bases is None else bases
    targets = _TARGETS if targets is None else targets
    out = []
    for name, bw, bh, bg, ratio in bases:
        for sc in scales:
            fn = "%s.png" % name if sc == 100 else "%s.scale-%d.png" % (name, sc)
            out.append((fn, _scaled(bw, sc), _scaled(bh, sc), bg, ratio))
    # Square44 的精确像素变体（三套主题：默认 / 深色 / 浅色）
    for t in targets:
        out.append(("Square44x44Logo.targetsize-%d.png" % t, t, t, None, 0.92))
    for t in targets:
        out.append(("Square44x44Logo.targetsize-%d_altform-unplated.png" % t, t, t, None, 0.92))
    for t in targets:
        out.append(("Square44x44Logo.targetsize-%d_altform-lightunplated.png" % t, t, t, None, 0.92))
    # AppList 别名（Windows 10 的 all-apps 列表读这一组）
    for t in targets:
        out.append(("AppList.targetsize-%d.png" % t, t, t, None, 0.92))
    return out


def generate(out_dir: str = OUT, src: str = ICON, plan=None) -> list:
    """生成全部资产，返回写入的文件列表。"""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, w, h, bg, ratio in (plan or _plan()):
        path = os.path.join(out_dir, name)
        render(src, w, h, bg, ratio).save(path)
        written.append(path)
    return written


def verify(out_dir: str = OUT, plan=None) -> bool:
    """检查资产齐全且尺寸正确（构建前的门禁）。"""
    import struct

    def png_size(path):
        with open(path, "rb") as f:
            head = f.read(33)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return w, h

    need = {name: (w, h) for name, w, h, _b, _r in (plan or _plan())}
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
