# -*- mode: python ; coding: utf-8 -*-
"""把真机截图（store/shots/src/）合成为商店可用的 1920x1080 截图。

背景：
  商店硬性要求截图 ≥1366x768。用户截的真机图大多是浮层/面板的局部裁切
  （605x239 ~ 784x981），直接上传会被拒；整张放大又会糊。
  所以统一铺一张 1920x1080 的底：
    · 有壁纸的浮层图 → 用它自己 cover 放大 + 高斯模糊 + 压暗当背景，
      前景原图按固定倍率居中放（不硬放大到全屏，文字保持锐利）；
    · 全屏屏保图 → 直接 cover 裁切成 1920x1080；
    · 两张竖版设置面板 → 并排合成一张（功能丰富度一眼看全）。

用法：
    .buildenv\\Scripts\\python.exe store\\make_real_shots.py

产物：store/shots/real-*.png（真机截图，进仓库留档，也直接上传 Partner Center）
"""
import os
import sys

from PIL import Image, ImageEnhance, ImageFilter, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "shots", "src")
OUT = os.path.join(BASE, "shots")
W, H = 1920, 1080


def _cover(src, w, h):
    """cover 缩放并居中裁剪到 (w, h)。"""
    s = max(w / src.width, h / src.height)
    im = src.resize((int(src.width * s + 0.5), int(src.height * s + 0.5)), Image.LANCZOS)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def _rrect(d, box, radius, **kw):
    """圆角矩形。PIL 7.2 还没有 ImageDraw.rounded_rectangle（8.2 才加），
    用「两个矩形 + 四个圆」拼出来，效果一致。"""
    x0, y0, x1, y1 = box
    r = radius
    d.rectangle([x0 + r, y0, x1 - r, y1], **kw)
    d.rectangle([x0, y0 + r, x1, y1 - r], **kw)
    d.ellipse([x0, y0, x0 + 2 * r, y0 + 2 * r], **kw)
    d.ellipse([x1 - 2 * r, y0, x1, y0 + 2 * r], **kw)
    d.ellipse([x0, y1 - 2 * r, x0 + 2 * r, y1], **kw)
    d.ellipse([x1 - 2 * r, y1 - 2 * r, x1, y1], **kw)


def _rounded(im, radius):
    """给 RGB 图加圆角 alpha，返回 RGBA。"""
    mask = Image.new("L", im.size, 0)
    _rrect(ImageDraw.Draw(mask), [0, 0, im.width - 1, im.height - 1],
           radius, fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def _drop_shadow(canvas, box, radius=26, blur=18, alpha=150):
    """在 canvas(RGBA) 上给 box 画一层柔和投影。"""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    _rrect(ImageDraw.Draw(layer), box, radius, fill=(0, 0, 0, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(layer)


def compose_card(src_names, out_name, fg_scale, blur=28, darken=0.45, gap=56):
    """通用合成：模糊背景 + 居中前景（可传多张并排）。"""
    srcs = [Image.open(os.path.join(SRC, n)).convert("RGB") for n in src_names]
    canvas = Image.new("RGBA", (W, H), (10, 12, 16, 255))

    if len(srcs) == 1:
        bg = _cover(srcs[0], W, H).filter(ImageFilter.GaussianBlur(blur))
        bg = ImageEnhance.Brightness(bg).enhance(darken)
        canvas = bg.convert("RGBA")
        fgs = [srcs[0]]
    else:
        # 多张并排：背景用一张干净的深色渐变（面板本身就是深色 UI）
        bg = Image.new("RGB", (W, H), (14, 16, 22))
        d = ImageDraw.Draw(bg)
        for y in range(H):
            t = y / float(H - 1)
            d.line([(0, y), (W, y)], fill=(int(14 + 8 * t), int(16 + 9 * t), int(22 + 12 * t)))
        canvas = bg.convert("RGBA")
        fgs = srcs

    scaled = [_rounded(_cover(f, int(f.width * fg_scale), int(f.height * fg_scale))
                       if fg_scale > 1 else f, 18) for f in fgs]
    total_w = sum(f.width for f in scaled) + gap * (len(scaled) - 1)
    x = (W - total_w) // 2
    for f in scaled:
        y = (H - f.height) // 2
        _drop_shadow(canvas, (x + 4, y + 10, x + f.width + 4, y + f.height + 10))
        canvas.alpha_composite(f, (x, y))
        x += f.width + gap

    out = canvas.convert("RGB")
    dst = os.path.join(OUT, out_name)
    out.save(dst, "PNG", optimize=True)
    print("  -> %s (%dx%d, %d KB)" % (os.path.relpath(dst, BASE), out.width, out.height,
                                      os.path.getsize(dst) // 1024))


def compose_fullbleed(src_name, out_name):
    """全屏图：直接 cover 裁成 1920x1080，不加任何东西。"""
    src = Image.open(os.path.join(SRC, src_name)).convert("RGB")
    out = _cover(src, W, H)
    dst = os.path.join(OUT, out_name)
    out.save(dst, "PNG", optimize=True)
    print("  -> %s (%dx%d, %d KB)" % (os.path.relpath(dst, BASE), out.width, out.height,
                                      os.path.getsize(dst) // 1024))


def main():
    if not os.path.isdir(SRC):
        sys.exit("没找到 %s —— 真机原图要先归档进去" % SRC)
    print("== 合成真机商店截图（1920x1080）==")
    compose_card(["real-02-card.png"], "real-1-overlay-card.png", fg_scale=1.6)
    compose_card(["real-03-native.png"], "real-2-native-float.png", fg_scale=1.6)
    compose_fullbleed("real-04-screensaver.png", "real-3-screensaver.png")
    compose_card(["real-05-settings-saver.png", "real-06-settings-sync.png"],
                 "real-4-settings.png", fg_scale=1.02, gap=48)
    compose_card(["real-01-idle.png"], "real-5-idle.png", fg_scale=1.9)
    print("完成。5 张都在 store/shots/（≥1366x768，可直接上传 Partner Center）")


if __name__ == "__main__":
    main()
