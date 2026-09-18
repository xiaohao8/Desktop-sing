# -*- coding: utf-8 -*-
"""离屏渲染商店截图素材（无显示器也能跑）

商店提审至少要 1 张截图（建议 1366×768+），仓库里一直没有现成素材。
这个脚本用 offscreen 平台真实实例化浮层，合成几张「像真机截图」的图：

  1. hero         —— 浮层在桌面壁纸上的实际效果（有歌词、有封面）
  2. idle         —— 无歌时的「等待播放…」占位（审核员第一眼看到的）
  3. settings     —— 设置面板（体现功能丰富度）

要点（踩过坑）：
  - **必须用 widget.grab()**，不能用 QWidget.render(pixmap)——后者在本环境
    采出来是全透明的，写出来的「像素断言」会恒真。
  - 抓之前要先 show()（offscreen 下不会真弹窗），否则尺寸可能是 0。

用法：.buildenv\\Scripts\\python.exe store\\render_shots.py
产物：store/out/shots/*.png
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import lyrics_overlay as ov  # noqa: E402
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap, QLinearGradient  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "shots")
os.makedirs(OUT, exist_ok=True)

W, H = 1600, 900          # 16:9，超过商店建议的 1366×768


def wallpaper() -> QPixmap:
    """合成一张干净的深色渐变壁纸（不引用任何第三方素材，免版权问题）"""
    pm = QPixmap(W, H)
    pm.fill(QColor("#0b1020"))
    p = QPainter(pm)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0.0, QColor("#131a2e"))
    g.setColorAt(0.5, QColor("#0d1222"))
    g.setColorAt(1.0, QColor("#181033"))
    p.fillRect(0, 0, W, H, g)
    # 两团柔光，让浮层的描边/光晕有东西可衬
    for cx, cy, r, col in ((380, 260, 420, QColor(60, 90, 170, 90)),
                           (1300, 700, 460, QColor(120, 70, 160, 80))):
        rg = QLinearGradient(cx - r, cy - r, cx + r, cy + r)
        rg.setColorAt(0.0, col)
        rg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(rg)
        p.setPen(Qt.NoPen)
        p.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
    p.end()
    return pm


def composite(bg: QPixmap, widget, x: int, y: int) -> QPixmap:
    """把控件真实渲染结果叠到壁纸上"""
    grab = widget.grab()
    if grab.isNull():
        raise SystemExit("grab() 失败：控件没 show() 或尺寸为 0")
    out = QPixmap(bg)
    p = QPainter(out)
    p.drawPixmap(x, y, grab)
    p.end()
    return out


def shot_idle(app) -> str:
    """无歌占位 —— 审核员装完第一眼看到的画面"""
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    ov_.resize(900, 260)
    ov_.show()
    app.processEvents()
    pm = composite(wallpaper(), ov_, (W - 900) // 2, H - 300)
    path = os.path.join(OUT, "1-idle.png")
    pm.save(path)
    return path


def shot_hero(app) -> str:
    """有歌词的实际效果（构造一首歌，走真实绘制路径）"""
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    ov_.song = {"title": "起风了", "artist": "买辣椒也用券"}
    ov_.lines = [[0.0, "这一路上走走停停"],
                 [3.0, "顺着少年漂流的痕迹"],
                 [6.5, "迈出车站的前一刻"],
                 [10.0, "竟有些犹豫"]]
    ov_.words = {0: [[0.0, 0.4, "这"], [0.4, 0.4, "一"], [0.8, 0.4, "路"],
                     [1.2, 0.4, "上"], [1.6, 0.4, "走"], [2.0, 0.4, "走"],
                     [2.4, 0.4, "停"], [2.8, 0.4, "停"]]}
    ov_.cur_idx = 0
    ov_.status = "PLAYING"
    ov_._fill = 0.55
    ov_.accent1 = QColor("#7dd3fc")
    ov_.accent2 = QColor("#c4b5fd")
    ov_.bg_color = ov_.pill_bg_color(ov_.accent1) if hasattr(ov_, "pill_bg_color") \
        else QColor(20, 23, 31, 220)
    ov_.resize(1000, 300)
    ov_.show()
    app.processEvents()
    ov_.update()
    app.processEvents()
    pm = composite(wallpaper(), ov_, (W - 1000) // 2, H - 340)
    path = os.path.join(OUT, "2-hero.png")
    pm.save(path)
    return path


def shot_settings(app) -> str:
    """设置面板。注意：offscreen 下控件需要几轮事件循环才完成布局与绘制，
    直接 grab 会抓到纯背景，所以要 processEvents + repaint 多轮后再抓。"""
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    panel = ov.SettingsPanel(ov_)
    panel.resize(1000, 860)
    panel.show()
    for _ in range(8):
        app.processEvents()
    panel.repaint()
    app.processEvents()
    grab = panel.grab()
    path = os.path.join(OUT, "3-settings.png")
    grab.save(path)
    return path


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("桌面歌词")
    ov._load_fonts()

    made = []
    for fn in (shot_idle, shot_hero, shot_settings):
        try:
            p = fn(app)
            sz = os.path.getsize(p)
            w = h = 0
            pm = QPixmap(p)
            w, h = pm.width(), pm.height()
            made.append((os.path.basename(p), w, h, sz))
            print("  ✓ %-16s %dx%d  %.0f KB" % (os.path.basename(p), w, h, sz / 1024))
        except Exception:
            import traceback
            print("  ✗ %s 失败：%s" % (fn.__name__, traceback.format_exc().splitlines()[-1]))

    print("\n产物目录：%s" % OUT)
    print("共 %d 张" % len(made))
    if not made:
        sys.exit(1)
    # 商店要求 1366×768+，这里自检一下
    small = [m for m in made if m[1] < 1366 or m[2] < 768]
    if small:
        print("⚠️ 以下小于商店建议的 1366×768：%s" % ", ".join(m[0] for m in small))


if __name__ == "__main__":
    main()
