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
  - ★ **所有「淡入动画」都必须手动推到终态再抓图**。offscreen 下没有真实
    event loop，QVariantAnimation 不会自己推进、时间也不会流逝，于是：
      · 设置面板 `showEvent()` 里的 180ms 淡入停在 opacity=0 → 抓出来是**纯背景**
        （grab() 返回的 pixmap 非 null，所以不会抛错，只是全透明——静默失败）；
      · 浮层切行动画把 `_line_t` 停在 0，而 `_apply_line_anim()`
        会 `setOpacity(_smoothstep(0) == 0)` → **整行歌词透明**，截图里只剩歌名。
    所以抓之前必须显式置终态：面板 `_fade.stop() + _fx.setOpacity(1.0)`，
    浮层 `_line_anim.stop() + _line_t = 1.0`。
  - 歌曲内容用**自写的占位歌词**，不要用真实歌曲的歌名与歌词：这张图是要
    传给商店当商品页素材的（对外发布物），嵌真实歌词属不必要的版权暴露。

用法：.buildenv\\Scripts\\python.exe store\\render_shots.py
产物：store/out/shots/*.png（1600×900，超过商店要求的 1366×768）
"""
import os
import sys
import time

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


def _has_content(pm: QPixmap, alpha_thresh: int = 8) -> bool:
    """抓到的图里是否真有内容（不是全透明的空壳）。

    为什么需要这个：控件还没真正绘制完成时，`grab()` 返回的是
    **非 null、但每个像素 alpha 都是 0** 的图，`isNull()` 判不出来，
    于是「空白截图」会一路流到商店提审材料里（实测设置面板就中过这一枪）。
    这里按网格采样 alpha，整张全透明才判空白。
    """
    img = pm.toImage()
    w, h = img.width(), img.height()
    if w == 0 or h == 0:
        return False
    step = max(1, min(w, h) // 40)
    for yy in range(0, h, step):
        for xx in range(0, w, step):
            if img.pixelColor(xx, yy).alpha() > alpha_thresh:
                return True
    return False


def composite(bg: QPixmap, widget, x: int, y: int, pixmap=None) -> QPixmap:
    """把控件真实渲染结果叠到壁纸上。
    pixmap 非空时直接用这张已抓好的图（用于要先 grab 再算居中位置的场合）。"""
    grab = pixmap if pixmap is not None else widget.grab()
    if grab.isNull():
        raise SystemExit("grab() 失败：控件没 show() 或尺寸为 0")
    if not _has_content(grab):
        raise SystemExit("grab() 得到全透明图（fade 动画没推到终态？）：%s"
                         % type(widget).__name__)
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
    ov_._relayout()
    ov_.show()
    app.processEvents()
    grab = ov_.grab()
    pm = composite(wallpaper(), ov_, (W - grab.width()) // 2,
                   H - grab.height() - 70, pixmap=grab)
    path = os.path.join(OUT, "store-shot-1-idle.png")
    pm.save(path)
    return path


def shot_hero(app) -> str:
    """有歌词的实际效果（构造一首歌，走真实绘制路径）

    构造方式与 `lyrics_overlay.py` 里的绘制自检保持一致（那边也是这么摆的），
    因为绘制读的是**缓存文本**而不是 `lines[cur_idx]`：
      · `_current_text` / `_next_text` —— 由 `_tick()` 从 `lines` 推出来；
        不手动喂 → 当前行是空字符串，画面里只剩歌名（hero 图曾经就是这个问题）；
      · `anchor_ts` —— 初值 0.0，配 `status="PLAYING"` 会让 `_current_pos()`
        等于「开机以来的秒数」，时间轴飞到天外，行号全乱；
      · `_line_t` —— 切行动画把整行 opacity 乘成 0，必须推到 1.0。
    """
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    # 自写占位内容（不用真实歌曲）：歌名/歌词都会进商品页截图，属对外发布物
    ov_.song = {"title": "示例歌曲", "artist": "演示歌手", "source": "demo", "cover": None}
    ov_.lines = [[0.0, "这一句会逐字高亮显示"],
                 [3.0, "光标走过就换下一行"],
                 [6.5, "拖动浮层可自由摆放"],
                 [10.0, "托盘图标可打开设置"]]
    _ch = list(ov_.lines[0][1])
    ov_.words = {0: [(i * 0.42, 0.42, c) for i, c in enumerate(_ch)]}
    ov_.status = "PLAYING"
    ov_.cur_idx = 0
    ov_._current_text = ov_.lines[0][1]
    ov_._next_text = ov_.lines[1][1]
    ov_.anchor_pos = 0.0
    ov_.anchor_ts = time.monotonic()
    ov_._line_anim.stop()
    ov_._line_t = 1.0
    ov_._fill = 0.55                  # 逐字高亮填到一半，一眼看出是卡拉OK
    ov_.accent1 = QColor("#7dd3fc")
    ov_.accent2 = QColor("#c4b5fd")
    ov_.bg_color = ov_.pill_bg_color(ov_.accent1) if hasattr(ov_, "pill_bg_color") \
        else QColor(20, 23, 31, 220)
    ov_.resize(1000, 320)
    ov_._relayout()
    ov_.show()
    app.processEvents()
    ov_.update()
    app.processEvents()
    # 先 grab 再按实际尺寸居中：`_relayout()` 可能把窗口自适应成别的尺寸，
    # 写死的坐标会让浮层偏出画面
    grab = ov_.grab()
    pm = composite(wallpaper(), ov_, (W - grab.width()) // 2,
                   H - grab.height() - 70, pixmap=grab)
    path = os.path.join(OUT, "store-shot-2-hero.png")
    pm.save(path)
    return path


def shot_settings(app) -> str:
    """设置面板。注意：offscreen 下控件需要几轮事件循环才完成布局与绘制，
    直接 grab 会抓到纯背景，所以要 processEvents + repaint 多轮后再抓。

    面板本体只有 548 宽，直接抓出来远小于商店要求的 1366×768。
    这里把面板贴到 1600×900 的桌面底上（与另外两张同规格），
    既是真实观感，也一并满足尺寸门槛。
    """
    watcher = ov.MediaWatcher()
    ov_ = ov.LyricOverlay(watcher)
    panel = ov.SettingsPanel(ov_)
    panel.resize(620, 880)
    panel.show()
    for _ in range(8):
        app.processEvents()
    # ★ showEvent() 里的淡入动画在 offscreen 下不推进，opacity 停在 0.0，
    #   直接 grab() 会得到一张「非 null 但全透明」的图——不抛错，静默变纯背景图。
    panel._fade.stop()
    panel._fx.setOpacity(1.0)
    panel.repaint()
    app.processEvents()
    grab = panel.grab()      # composite() 会自证「不是全透明空图」
    # 贴到桌面底：面板居中，(H - 面板高) / 2 保证上下留白相等
    pm = composite(wallpaper(), panel, (W - grab.width()) // 2,
                   max(0, (H - grab.height()) // 2),
                   pixmap=grab)
    path = os.path.join(OUT, "store-shot-3-settings.png")
    pm.save(path)
    return path


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("桌面歌词")
    ov._load_fonts()

    made = []
    failed = []
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
            failed.append(fn.__name__)
            print("  ✗ %s 失败：%s" % (fn.__name__, traceback.format_exc().splitlines()[-1]))

    print("\n产物目录：%s" % OUT)
    print("共 %d 张%s" % (len(made), "，失败 %d 张" % len(failed) if failed else ""))
    if not made:
        sys.exit(1)
    # 商店要求 1366×768+，这里自检一下
    small = [m for m in made if m[1] < 1366 or m[2] < 768]
    if small:
        print("⚠️ 以下小于商店建议的 1366×768：%s" % ", ".join(m[0] for m in small))
    # 少一张都是缺素材（三张分别对应「等待态 / 有歌词 / 设置面板」，
    # 少「有歌词」那张等于商品页看不到核心功能），所以按失败处理
    if failed or small:
        sys.exit(1)


if __name__ == "__main__":
    main()
