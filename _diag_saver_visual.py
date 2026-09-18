# -*- coding: utf-8 -*-
"""氛围屏保「视觉质量」量化巡检：把"好不好看"变成可测量的数。

肉眼看缩略图会骗人（缩放、压缩、显示器 gamma），所以这里只输出硬指标，
用于 Pass 2/3 的改前改后对照：

  A. 硬接缝 —— 只在**动画带的上/下边界**上测亮度阶跃，且把文字层 stub 掉再渲染。
     为什么必须这样测：文字笔画自身的边缘、音浪的公共基线，都是合法的硬边；
     上一版直接在全图上找"最大行阶跃"，找出来的全是文字边缘，等于没查。
     真正的病症是：动画带的径向渐变没衰减到 0 就被 fillRect 裁掉，
     带边界留下一条 6~13/255 的可见接缝。
  B. 亮度分布 —— 均值 / 前 0.05% / 峰值 / 点亮像素占比。OLED 防烧屏要峰值低。
  C. 静态残留 —— 整个换位周期里每个像素被点亮的帧占比。
     OLED 烧屏看的是**平均**占空比，不是瞬时亮度。这里报最大占空比、
     以及"点亮像素里有多大的比例半程以上都在亮"（这才是烧屏风险面积）。

用法：
    python _diag_saver_visual.py                       # 全部风格，1920x1080
    python _diag_saver_visual.py --style bars
    python _diag_saver_visual.py --size 3440x1440
    python _diag_saver_visual.py --cmp preview/saver_ab_before   # 与打磨前的图对照
"""
import argparse
import os
import random
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import _cfg_sandbox                                            # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

import lyrics_overlay as L                                     # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QBrush, QImage  # noqa: E402
from PySide6.QtCore import Qt                                  # noqa: E402
from PIL import Image, ImageFilter                             # noqa: E402

app = QApplication(sys.argv)
L._load_fonts()
ov = L.LyricOverlay(L.MediaWatcher())
cov = QPixmap(500, 500)
_p = QPainter(cov)
_g = QLinearGradient(0, 0, 500, 500)
_g.setColorAt(0.0, QColor("#ff8a3d"))
_g.setColorAt(0.45, QColor("#e0407a"))
_g.setColorAt(1.0, QColor("#4a3aff"))
_p.fillRect(0, 0, 500, 500, QBrush(_g))
_p.end()
ov.cover_pix = cov
ov.accent1, ov.accent2 = L.extract_accent(cov)
ov.song = {"title": "夜航西飞", "artist": "陈粒", "source": "qq"}
ov._current_text, ov._next_text = "夜色温柔", "风也温柔"

OUT = os.path.join(APP_DIR, "preview", "saver_visual")
os.makedirs(OUT, exist_ok=True)

STYLES = ["particle", "minimal", "bars", "orbits"]
PERIOD = L.AmbientSaver.ANCHOR_HOLD + L.AmbientSaver.ANCHOR_MOVE
CYCLE = PERIOD * L.AmbientSaver.ANCHORS
ANIM_METHODS = ("_draw_particle_glow", "_draw_particles", "_draw_bars", "_draw_orbits")


def as_l(pm):
    img = pm.toImage()
    if img.format() != QImage.Format_Grayscale8:
        img = img.convertToFormat(QImage.Format_Grayscale8)
    w, h = img.width(), img.height()
    return Image.frombytes("L", (w, h), bytes(img.constBits()),
                           "raw", "L", img.bytesPerLine(), 1)


def sample(style, w, h, t, text=True):
    """渲染一帧。text=False 时把文字层 stub 掉，只留动画。"""
    sv = L.AmbientSaver(ov)
    sv.ov.saver_style = style
    sv.resize(w, h)
    sv._t0 = time.monotonic() - t
    sv._p_t0 = time.monotonic() - t
    random.seed(20260918)
    sv._particles = None
    sv._p_geom = None
    sv._timer.stop()
    plan = sv._plan(w, h, t)
    if not text:
        sv._draw_text_block = lambda *a, **k: None
    pm = QPixmap(w, h)
    pm.fill(Qt.black)
    sv.render(pm)
    sv.deleteLater()
    return pm, plan


def row_means(im, step=3):
    px = im.load()
    w, h = im.size
    xs = range(0, w, step)
    n = len(xs)
    return [sum(px[x, y] for x in xs) / n for y in range(h)]


def edge_step(prof, y, span=3):
    """跨越 y 这一行的平均亮度阶跃（带边界两侧对比）"""
    n = len(prof)
    if y - span < 1 or y + span > n:
        return 0.0
    a = sum(prof[y - span:y]) / span
    b = sum(prof[y:y + span]) / span
    return abs(b - a)


def max_step(prof, span=3):
    best, at = 0.0, -1
    for i in range(span, len(prof) - span):
        d = abs(sum(prof[i:i + span]) / span - sum(prof[i - span:i]) / span)
        if d > best:
            best, at = d, i
    return best, at


def stats(im):
    hgram = im.histogram()
    tot = im.size[0] * im.size[1]
    mean = sum(v * c for v, c in enumerate(hgram)) / tot
    peak = max(v for v, c in enumerate(hgram) if c > 0)
    p99 = next(v for v in range(255, -1, -1) if sum(hgram[v:]) >= tot * 0.0005)
    return mean, p99, peak, sum(hgram[9:]) / tot


def lit_grid(im, block=5):
    """把图按 block×block 取最大值再抽样，得到点亮网格。

    注意 PIL 的 MaxFilter 只接受**奇数**尺寸（偶数会抛 bad filter size），
    所以 block 取 5 而不是 4；resize(NEAREST) 之后每个输出像素
    正好等于对应 5x5 邻域的最大值。
    """
    w, h = im.size
    mask = im.point(lambda v: 255 if v > 8 else 0)
    small = mask.filter(ImageFilter.MaxFilter(block)).resize(
        (w // block, h // block), Image.NEAREST)
    return list(small.getdata()), w // block, h // block


def luma_grid(im, block=5):
    """block×block 的平均亮度网格（BOX 均值），用来算「周期内累计亮度」"""
    w, h = im.size
    small = im.resize((w // block, h // block), Image.BOX)
    return list(small.getdata()), w // block, h // block


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default=None)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--cmp", default=None, help="旧 PNG 目录，做改前改后对照")
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()
    styles = [a.style] if a.style else STYLES
    w, h = (int(v) for v in a.size.lower().split("x"))
    T0 = time.time()

    def hdr(s):
        print("=" * 100)
        print(s)
        print("=" * 100)

    # ---------------------------------------------------------------- A
    hdr("A. 硬接缝：只在动画带的上/下边界测（动画层单独渲染，排除文字自身边缘）")
    print("%-9s %-8s %-16s %-16s %-18s %s" %
          ("风格", "t(s)", "上边界阶跃", "下边界阶跃", "全图最大行阶跃", "判定"))
    print("-" * 100)
    problems = []
    for style in styles:
        for t in (PERIOD * 0.25, PERIOD + PERIOD * 0.25):
            pm, plan = sample(style, w, h, t, text=False)
            im = as_l(pm)
            prof = row_means(im)
            band = plan["band"]
            if band is None:
                print("%-9s %-8.0f %-16s %-16s %-18s %s" %
                      (style, t, "-", "-", "-", "无动画带（minimal）"))
                continue
            st = edge_step(prof, int(round(band.top())))
            sb = edge_step(prof, int(round(band.bottom())))
            any_s, any_at = max_step(prof)
            bad = []
            if st > 1.0:
                bad.append("上边界接缝 %.2f" % st)
            if sb > 1.0:
                bad.append("下边界接缝 %.2f" % sb)
            if bad:
                problems.append(("A", style, t, "; ".join(bad)))
            print("%-9s %-8.0f %-16s %-16s %-18s %s" %
                  (style, t, "%.2f" % st, "%.2f" % sb,
                   "%.2f@y=%d" % (any_s, any_at),
                   ("!! " + "; ".join(bad)) if bad else "ok"))

    # ---------------------------------------------------------------- B
    print()
    hdr("B. 亮度分布（合成图，含文字）")
    print("%-9s %-8s %-10s %-10s %-9s %-11s %s" %
          ("风格", "t(s)", "均值", "前0.05%", "峰值", "点亮占比", "判定"))
    print("-" * 100)
    for style in styles:
        for t in (PERIOD * 0.25, PERIOD + PERIOD * 0.25):
            pm, plan = sample(style, w, h, t)
            mean, p99, peak, lit = stats(as_l(pm))
            bad = []
            if p99 > 150:
                bad.append("前0.05%%过亮 %.0f" % p99)
            if style != "minimal" and lit < 0.0008:
                bad.append("点亮占比过低 %.4f%%（动画几乎看不见）" % (lit * 100))
            if bad:
                problems.append(("B", style, t, "; ".join(bad)))
            print("%-9s %-8.0f %-10.2f %-10.0f %-9d %-11s %s" %
                  (style, t, mean, p99, peak, "%.3f%%" % (lit * 100),
                   ("!! " + "; ".join(bad)) if bad else "ok"))
            if not a.no_save and t > PERIOD:
                pm.save(os.path.join(OUT, "%s_%dx%d.png" % (style, w, h)))

    # ---------------------------------------------------------------- C
    print()
    hdr("C. 静态残留：整个换位周期内逐像素统计（OLED 烧屏看**累计亮度**，不看瞬时）")
    print("周期 = %d 档 × %.0fs = %.0fs，取 %d 帧。" %
          (L.AmbientSaver.ANCHORS, PERIOD, CYCLE, 10))
    print("「占空比」只说明亮没亮（阈值仅 8/255），真正决定烧屏的是**周期内平均亮度**。")
    print("%-9s %-10s %-22s %-11s %-14s %s" %
          ("风格", "最大占空比", "半程以上在亮的点位", "均占空比",
           "平均亮度 max/p99", "判定"))
    print("-" * 100)
    N = 10
    for style in styles:
        masks, lumas = [], []
        gw = gh = 0
        for i in range(N):
            im = as_l(sample(style, w, h, i * CYCLE / N)[0])
            g, gw, gh = lit_grid(im)
            l, _, _ = luma_grid(im)
            masks.append(g)
            lumas.append(l)
        n = gw * gh
        ever = over50 = 0
        tot_duty = 0
        mx_duty = 0
        loads = []
        for k in range(n):
            c = 0
            s = 0
            for i in range(N):
                if masks[i][k]:
                    c += 1
                s += lumas[i][k]
            if c:
                ever += 1
                tot_duty += c
                if c > mx_duty:
                    mx_duty = c
                if c > N / 2:
                    over50 += 1
            loads.append(s / float(N))
        duty = mx_duty / float(N)
        mean_duty = (tot_duty / ever / N) if ever else 0.0
        loads.sort(reverse=True)
        lmax = loads[0]
        lp99 = loads[max(0, int(len(loads) * 0.01))]
        risk = 100.0 * over50 / max(1, ever)
        bad = []
        # 判定口径：
        #  · 半程以上在亮的点位超过点亮面积的 60% → 大片区域长期固定点亮，是真风险
        #  · 周期内平均亮度 99 分位 > 80/255（约 31% 灰长期不灭）→ 也是真风险
        if risk > 60.0:
            bad.append("半程以上在亮占 %.1f%%" % risk)
        if lp99 > 80:
            bad.append("平均亮度 99 分位 %.0f 偏高" % lp99)
        if bad:
            problems.append(("C", style, -1.0, "; ".join(bad)))
        print("%-9s %-10s %-22s %-11s %-14s %s" %
              (style, "%.0f%%" % (duty * 100),
               "%d / %d（%.2f%%）" % (over50, ever, risk),
               "%.0f%%" % (mean_duty * 100),
               "%.0f / %.0f" % (lmax, lp99),
               ("!! " + "; ".join(bad)) if bad else "ok"))

    # ---------------------------------------------------------------- 对照
    if a.cmp and os.path.isdir(a.cmp):
        print()
        hdr("D. 改前 / 改后对照（同一条量化口径）")
        print("%-9s %-22s %-22s %s" % ("风格", "旧图 均值/前0.05%/点亮", "新图 均值/前0.05%/点亮", "变化"))
        print("-" * 100)
        for style in styles:
            fn = "%s_%dx%d.png" % (style, w, h)
            op = os.path.join(a.cmp, fn)
            np_ = os.path.join(OUT, fn)
            if not (os.path.exists(op) and os.path.exists(np_)):
                print("%-9s %s" % (style, "(缺图，跳过)"))
                continue
            o = stats(Image.open(op).convert("L"))
            nn = stats(Image.open(np_).convert("L"))
            print("%-9s %-22s %-22s 均值 %+.2f / 前0.05%% %+.0f / 点亮 %+.3fpp" %
                  (style,
                   "%.2f / %.0f / %.3f%%" % (o[0], o[1], o[3] * 100),
                   "%.2f / %.0f / %.3f%%" % (nn[0], nn[1], nn[3] * 100),
                   nn[0] - o[0], nn[1] - o[1], (nn[3] - o[3]) * 100))

    print()
    if problems:
        print("!! %d 处待打磨：" % len(problems))
        for s, st, t, m in problems:
            print("   [%s] %-9s t=%-7.0f %s" % (s, st, t, m))
    else:
        print("无待打磨项：带边界无接缝、无过亮块、无严重静态残留")
    print("样例图：%s   （用时 %.1fs）" % (OUT, time.time() - T0))

    ov.hotkeys.unregister()
    _cfg_sandbox.restore()
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
