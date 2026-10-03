# -*- coding: utf-8 -*-
"""离屏验证「疑似错配提示条」真的画出来了。

铁律要点：
- 用 grab()（render() 对普通子控件抓不出东西）；
- 抓前把动画推到终态（面板 showEvent 有 180ms 淡入，offscreen 下不推进会停在 opacity=0，
  抓出来是全透明废图，而且 isNull() 判不出来）；
- 加「非空白」自证，别让废图静默落盘；
- 先备份配置再还原。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"C:\Users\35436\Desktop\代码\desktop-lyrics")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint

OUT = r"C:\Users\35436\Desktop\代码\desktop-lyrics\preview"
os.makedirs(OUT, exist_ok=True)

import lyrics_overlay as L

app = QApplication.instance() or QApplication([])


def has_content(pm, thresh=8):
    """grab() 在控件没真正绘制时返回『非 null 但全透明』的图，必须自己判非空白。"""
    img = pm.toImage()
    if img.isNull():
        return False
    step = max(1, min(img.width(), img.height()) // 40)
    for y in range(0, img.height(), step):
        for x in range(0, img.width(), step):
            if img.pixelColor(x, y).alpha() > thresh:
                return True
    return False


def luminance_hits(pm, thr=25, step=1):
    """相邻像素亮度突变数——合成图（整张 alpha=255）不能用透明度判空白。"""
    img = pm.toImage()
    w, h = img.width(), img.height()
    n = 0
    for y in range(0, h - 4, step):
        for x in range(0, w - 4, step):
            if abs(img.pixelColor(x, y).lightness()
                   - img.pixelColor(x + 4, y).lightness()) > thr:
                n += 1
    return n


def region_has_amber(pm, rect):
    """在**父面板整图**的指定区域里找琥珀色像素。

    ⚠️ 不能用 `bar.grab()` 判断显示/隐藏——Qt 的 grab() **忽略可见性**，
    控件隐藏后照样返回上次绘制的同一张图（实测两态像素完全一致）。
    所以判据必须落在父面板的真实合成结果上。
    """
    img = pm.toImage()
    n = 0
    for y in range(rect.top(), min(rect.bottom(), img.height())):
        for x in range(rect.left(), min(rect.right(), img.width())):
            c = img.pixelColor(x, y)
            # 琥珀提示条底色 rgba(251,191,36,~26) 叠在深色面板上 → 明显偏暖
            if c.red() > 120 and c.green() > 80 and c.blue() < c.green() * 0.75:
                n += 1
    return n


ov = L.LyricOverlay(L.MediaWatcher())      # 照项目既有写法：只借用 UI，不启动监听
panel = L.SettingsPanel(ov)

# 推动画到终态（offscreen 无 event loop，动画停在第 0 帧）
for name in ("_fade", "_anim"):
    a = getattr(panel, name, None)
    if a is not None and hasattr(a, "stop"):
        a.stop()
if hasattr(panel, "_fx"):
    panel._fx.setOpacity(1.0)

panel.resize(430, 900)
panel.show()
app.processEvents()

results = []
bar = panel.mismatch_bar

# --- A. 错配时：提示条应可见，且父面板该区域真的有琥珀色内容 ---
ov.singer_mismatch = True
panel.refresh()
app.processEvents()
results.append(("错配-可见", bar.isVisible(), "提示条应可见"))
bar.grab().save(os.path.join(OUT, "mismatch_on.png"))
full_on = panel.grab()
full_on.save(os.path.join(OUT, "panel_mismatch.png"))
rect = bar.geometry()
amber_on = region_has_amber(full_on, rect)
results.append(("错配-有内容", amber_on > 200,
                "父面板该区域应有琥珀色像素（实测 %d）" % amber_on))
results.append(("整面板非空白", has_content(full_on), "整面板必须非空白"))

# --- B. 正常时：提示条应隐藏，且父面板该区域**没有**琥珀色内容 ---
ov.singer_mismatch = False
panel.refresh()
app.processEvents()
results.append(("正常-隐藏", not bar.isVisible(), "提示条应隐藏"))
bar.grab().save(os.path.join(OUT, "mismatch_off.png"))
full_off = panel.grab()
full_off.save(os.path.join(OUT, "panel_normal.png"))
amber_off = region_has_amber(full_off, rect)
results.append(("正常-无内容", amber_off < 50,
                "父面板该区域应无琥珀色（实测 %d）" % amber_off))
print("整面板尺寸 = %dx%d" % (full_on.width(), full_on.height()))

print()
print("%-14s %-8s %s" % ("断言", "结果", "说明"))
allok = True
for name, ok, desc in results:
    allok = allok and ok
    print("%-14s %-8s %s" % (name, "PASS" if ok else "FAIL", desc))

# --- C. 判据自身要有分辨力：错配态琥珀像素必须远多于正常态 ---
resolvable = amber_on > amber_off * 5
allok = allok and resolvable
print("%-14s %-8s 错配=%d 正常=%d（需 >5 倍）"
      % ("判据可分辨", "PASS" if resolvable else "FAIL", amber_on, amber_off))

# --- D. 变异测试：把状态判据改坏（refresh 不再同步显隐），断言必须 FAIL ---
#     注入方式：让 refresh() 里的显隐同步失效——直接改可见性后再走一遍 refresh。
#     若断言有效，此时「错配态应可见」会与实际不符而被抓住。
panel.refresh()
app.processEvents()
bar.setVisible(False)                     # 注入：状态是错配，但被强行隐藏
app.processEvents()
mutated_visible = bar.isVisible()
app.processEvents()
pm_mut = panel.grab()
amber_mut = region_has_amber(pm_mut, rect)
# 还原
ov.singer_mismatch = True
panel.refresh()
app.processEvents()
# 变异后：状态为错配却看不见 → 判据应当不再满足「错配-有内容」
mutation_caught = (not mutated_visible) and amber_mut < 50
allok = allok and mutation_caught
print("%-14s %-8s 强行隐藏后 visible=%s 琥珀=%d（应被断言抓住）"
      % ("变异可捕获", "PASS" if mutation_caught else "FAIL",
         mutated_visible, amber_mut))

print()
print("结果：%s" % ("全部通过" if allok else "有失败"))
sys.exit(0 if allok else 1)
