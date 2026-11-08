# -*- mode: python ; coding: utf-8 -*-
"""离屏重渲商店提审用的两张设置面板源图（src/real-05 / real-06）。

背景：src/ 里的面板截图是 v1.0.0 时代真机截的，头部徽章停留在 v1.0.0；
发新版本时用本脚本从当前源码离屏渲染（QT offscreen + widget.grab()），
替换后重跑 make_real_shots.py 即可得到带当前版本徽章的 real-4-settings.png。

要点（与 render_shots.py 同一套踩坑结论）：
  · offscreen 平台不带字体，必须 QT_QPA_FONTDIR 指向系统字体 + 手动
    addApplicationFont 装入仓库自带 MiSans，否则中文全是豆腐块；
  · showEvent() 的淡入动画在 offscreen 不推进，opacity 停 0 → 抓到全透明，
    必须 _fade.stop() + _fx.setOpacity(1.0) 推到终态；
  · 面板按真机尺寸 822×1140 渲染（内容高 2216，与真机一致地出滚动条）。

用法：
    .buildenv312\\Scripts\\python.exe store\\render_panel_shots.py             # 两张面板源图
    .buildenv312\\Scripts\\python.exe store\\render_panel_shots.py --idle-2x  # 待机胶囊 2× 重渲（合成更锐利）

产物（覆盖前先备份到 shots/src/backup-real-panel-v1.0.0/）：
    store/shots/src/real-05-settings-saver.png   滚到「氛围屏保」区
    store/shots/src/real-06-settings-sync.png    顶部：歌词同步 + 外观
"""
import os
import shutil
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
if "--idle-2x" in sys.argv:
    # 待机胶囊按 2× 设备像素渲染（须在 QApplication 创建前设置），
    # 合成放大后文字仍锐利；面板渲染走默认命令，不受影响。
    os.environ["QT_SCALE_FACTOR"] = "2"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import lyrics_overlay as ov  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea  # noqa: E402

SRC = os.path.join(ROOT, "store", "shots", "src")
BACKUP = os.path.join(SRC, "backup-real-panel-v1.0.0")

# 与其余 4 张合成图同一首歌，保持商品页叙事一致
SONG = {"title": "暮色回响 (Live)", "artist": "张碧晨/李承铉",
        "album": "", "source": "qq", "cover": None}

PANEL_W, PANEL_H = 822, 1140   # 真机设置面板尺寸（UIA 实测）


def load_fonts():
    n = 0
    for f in sorted(os.listdir(os.path.join(ROOT, "fonts"))):
        if f.lower().endswith((".ttf", ".otf")):
            if QFontDatabase.addApplicationFont(os.path.join(ROOT, "fonts", f)) >= 0:
                n += 1
    return n


def find_scroll(panel):
    sas = [sa for sa in panel.findChildren(QScrollArea) if sa.isVisible()]
    return sas[0] if sas else None


def scroll_to(sa, where):
    bar = sa.verticalScrollBar()
    if where == "top":
        bar.setValue(0)
        return
    # 锚到「悬浮窗」分节边界：视口顶部从分节卡片的留白处开始，
    # 避免像旧图那样把上一节的行裁一半留在画面顶端。
    target = None
    for lb in sa.widget().findChildren(QLabel):
        if (lb.text() or "").strip() == "悬浮窗":
            target = lb
            break
    if target is None:                   # 找不到就退回「氛围屏保」锚点
        for lb in sa.widget().findChildren(QLabel):
            if "氛围屏保" in (lb.text() or ""):
                target = lb
                break
    if target is None:
        bar.setValue(bar.maximum() // 3)
        return
    # 沿父链找「分节卡片」容器（滚动内容 widget 的直接子控件），对齐卡片顶边：
    # 标签离卡片顶还有内边距，直接用标签 y 会把上一节卡片的底边留在画面顶端。
    card = target.parentWidget()
    content = sa.widget()
    while card is not None and card.parentWidget() is not content:
        card = card.parentWidget()
    anchor = card if card is not None else target
    top = anchor.mapTo(content, QPoint(0, 0)).y()
    bar.setValue(max(0, top - 12))      # 上方只留分节间距的呼吸位


def trim_alpha(img):
    """裁掉四周的透明边（面板圆角/阴影留白），只留不透明内容区。"""
    box = img.getbbox()
    return img.crop(box) if box else img


def render_one(app, fname, where, h=None):
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    ov_.song = dict(SONG)
    # 商店版如实取景：STORE_MODE 下不渲染 进程保活/更新地址 等（与提审包一致）
    ov.STORE_MODE = True
    # 播放态（去掉「（已暂停）」后缀，与其余 4 张合成图的播放观感一致）
    ov_.status = "PLAYING"
    # 暖色假封面 -> 封面取色得到金色主题（与其余 4 张合成图色调一致）
    from PySide6.QtGui import QPixmap
    warm = QPixmap(64, 64)
    warm.fill(ov.QColor("#c98f3d"))
    ov_.cover_pix = warm
    ov_.panel = None
    ov_._resolve_accent()
    panel = ov.SettingsPanel(ov_)
    panel.resize(PANEL_W, h or PANEL_H)
    panel.show()
    for _ in range(8):
        app.processEvents()
    panel._fade.stop()
    panel._fx.setOpacity(1.0)
    sa = find_scroll(panel)
    if sa is not None:
        scroll_to(sa, where)
    else:
        print("  ! 未找到 QScrollArea，按未滚动渲染")
    panel.repaint()
    for _ in range(4):
        app.processEvents()
    pm = panel.grab().toImage()
    if pm.isNull():
        raise SystemExit("grab 返回空图，中止不覆盖源图")
    path = os.path.join(SRC, fname)
    tmp = path + ".tmp.png"
    if not pm.save(tmp):
        raise SystemExit("保存失败: %s" % path)
    from PIL import Image
    img = trim_alpha(Image.open(tmp).convert("RGBA"))
    img.save(path)
    os.remove(tmp)
    print("  ✓ %s  %dx%d  scroll=%s" % (fname, img.width, img.height, where))
    panel.close()
    ov_.close()


def render_idle_bar(app):
    """空闲态歌词条源图：1.0.3 起待机文案为双语「桌面歌词已就绪 · Ready」
    （商店审核 10.1.2.10 曾把「等待播放…」误读为无限加载），旧真机图
    real-01-idle.png 里的文案已过时，这里从当前源码离屏重渲。

    产物：src/real-01b-idle-bar.png（带 alpha 的待机卡片），
    由 make_real_shots.py 合成到 real-5-idle.png 的模糊壁纸底上。"""
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    ov_.style_mode = "glass"        # 与旧真机图相同的玻璃胶囊样式（属性名是 style_mode）
    ov_._ctrl_t = 0.0               # 悬停控制条不进画面
    ov_._ctrl_anim.stop()
    ov_._relayout()
    ov_.show()
    for _ in range(8):
        app.processEvents()
    ov_.repaint()
    for _ in range(4):
        app.processEvents()
    pm = ov_.grab().toImage()
    if pm.isNull():
        raise SystemExit("空闲态 grab 返回空图，中止")
    path = os.path.join(SRC, "real-01b-idle-bar.png")
    tmp = path + ".tmp.png"
    if not pm.save(tmp):
        raise SystemExit("保存失败: %s" % path)
    from PIL import Image
    img = trim_alpha(Image.open(tmp).convert("RGBA"))
    img.save(path)
    os.remove(tmp)
    print("  ✓ real-01b-idle-bar.png  %dx%d（桌面歌词已就绪 · Ready）" % (img.width, img.height))
    ov_.close()


def main():
    app = QApplication(sys.argv)
    print("[字体] 装入 MiSans %d 个字重" % load_fonts())
    os.makedirs(BACKUP, exist_ok=True)
    for fname in ("real-05-settings-saver.png", "real-06-settings-sync.png"):
        b = os.path.join(BACKUP, fname)
        if not os.path.exists(b):
            shutil.copy2(os.path.join(SRC, fname), b)
    print("[备份] 旧源图 -> %s" % os.path.relpath(BACKUP, ROOT))
    if "--idle-2x" in sys.argv:
        render_idle_bar(app)
        print("[完成] 待机胶囊已按 2× 重渲；重跑 make_real_shots.py 合成 real-5")
        return
    # saver 那张面板用 1100 高：STORE_MODE 内容 ~2078px，视口越短滚动上限越高，
    # 否则 setValue 被钳到 max，上一节（字体库）卡片的底边必然留在画面顶端。
    render_one(app, "real-05-settings-saver.png", "saver", h=1060)
    render_one(app, "real-06-settings-sync.png", "top")
    render_idle_bar(app)
    print("[完成] 重跑 make_real_shots.py 合成 real-4 / real-5")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
