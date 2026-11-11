# -*- coding: utf-8 -*-
"""端到端排查：构造真实 SettingsPanel，逐个控件模拟滚轮，抓任何漏装守卫的控件。

与 _test_wheel_guard.py 的区别：那个测的是提取出来的守卫类，这个测的是
真实面板的 _build() 安装结果（能抓到「动态创建的控件漏装」这类细节问题）。
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QScrollArea, QSlider)

import lyrics_overlay as L

app = QApplication.instance() or QApplication([])
fails = []

def chk(desc, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + desc + " -> %r" % (got,))
    if not ok:
        fails.append(desc)

def wheel(w, dy=-120, pixels=0):
    ev = QWheelEvent(QPointF(9, 9), QPointF(9, 9),
                     QPoint(0, pixels), QPoint(0, dy),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)
    app.processEvents()

# ---- 造一个够用的假 LyricOverlay（只提供数值/字符串属性，方法由 MagicMock 兜底）----
ov = MagicMock()
ov.accent1 = QColor("#4a9eff")
for k, v in dict(offset=0.0, font_scale=1.0, opacity=1.0, edge_fade_px=20,
                 idle_min=5, font_family="", cfg={}, style_mode="glass",
                 anim_style="slide", saver_style="particles", color_mode="auto",
                 color_theme="default", display_mode="normal",
                 _current_text="", _next_text="", song=None).items():
    setattr(ov, k, v)
for k in ("show_cover", "show_time", "show_trans", "glow", "edge_fade",
          "click_through", "locked", "keepalive", "hotkeys_on", "pause_fade",
          "idle_saver", "saver_idle_only", "update_auto"):
    setattr(ov, k, False)

panel = L.SettingsPanel(ov)
panel.show()
app.processEvents()
print("== 真实面板构造 ==")
chk("守卫对象已创建", isinstance(getattr(panel, "_wheel_guard", None), L._WheelToScroll), True)
scroll = panel._scroll_area
chk("滚动区域是 QScrollArea", isinstance(scroll, QScrollArea), True)

sliders = panel.findChildren(QSlider)
combos = panel.findChildren(QComboBox)
print("面板内 QSlider %d 个 / QComboBox %d 个" % (len(sliders), len(combos)))
chk("滑条数量符合预期", len(sliders) >= 4, True)
chk("下拉框数量符合预期", len(combos) >= 4, True)

# ---- 逐个控件发滚轮：任何一个漏装守卫都会改值 ----
before = {}
for w in sliders + combos:
    before[id(w)] = w.value() if isinstance(w, QSlider) else w.currentIndex()
sb = scroll.verticalScrollBar()
start = sb.value()
for w in sliders + combos:
    wheel(w, -120)
changed = []
for w in sliders + combos:
    now = w.value() if isinstance(w, QSlider) else w.currentIndex()
    if now != before[id(w)]:
        changed.append((w.objectName() or type(w).__name__, before[id(w)], now))
print("== 逐个控件滚轮（angleDelta） ==")
chk("没有任何控件被滚轮改值", changed, [])
chk("页面确实滚动了", sb.value() > start, True)

# ---- pixelDelta（真实触控板常见）----
before2 = {}
for w in sliders + combos:
    before2[id(w)] = w.value() if isinstance(w, QSlider) else w.currentIndex()
sb.setValue(sb.minimum())
s2 = sb.value()
print("pixelDelta 起点 s2=%d / max=%d" % (s2, sb.maximum()))
for w in sliders + combos:
    wheel(w, 0, pixels=-60)
changed2 = [w for w in sliders + combos
            if (w.value() if isinstance(w, QSlider) else w.currentIndex()) != before2[id(w)]]
print("== pixelDelta 触控板滚轮 ==")
chk("pixelDelta 不改值", changed2, [])
chk("pixelDelta 能滚动页面", sb.value() > s2, True)

# ---- 下拉框弹层里滚轮仍应能滚动选项（守卫不能误伤弹层）----
combo = combos[0]
try:
    combo.showPopup()
    app.processEvents()
    view = combo.view()
    idx0 = combo.currentIndex()
    wheel(view.viewport() if hasattr(view, "viewport") else view, -120)
    print("== 弹层滚轮 ==  弹层内 index %d -> %d（不强制断言，offscreen 下弹层可能不接收事件）"
          % (idx0, combo.currentIndex()))
except Exception as e:
    print("== 弹层滚轮 ==  跳过（%s）" % type(e).__name__)

panel._rt.stop()
panel.close()
print()
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL PASS")
