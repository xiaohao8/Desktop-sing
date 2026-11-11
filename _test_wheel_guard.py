# -*- coding: utf-8 -*-
"""设置面板滚轮守卫回归测试（真实 PySide6，offscreen）。

从 lyrics_overlay.py 用 AST 提取 _WheelToScroll 类源码执行，保证测的就是线上代码：
  - 装守卫后：滚轮落在 QSlider / QComboBox 上 → 值不变，页面滚动条滚动
  - 对照组（不装守卫）：滚轮改值（复现原 bug）
  - 下拉框弹层、非滚轮事件不受影响
"""
import ast, io, os, sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QScrollArea, QSlider,
                              QVBoxLayout, QWidget)

# ---- 从主文件提取真实类定义，避免测试与实现两套代码漂移 ----
src = io.open("lyrics_overlay.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body
           if isinstance(n, ast.ClassDef) and n.name == "_WheelToScroll")
mod = ast.Module(body=[cls], type_ignores=[])
ast.fix_missing_locations(mod)
ns = dict(globals())
exec(compile(mod, "lyrics_overlay.py:_WheelToScroll", "exec"), ns)
WheelToScroll = ns["_WheelToScroll"]

app = QApplication.instance() or QApplication([])
fails = []

def chk(desc, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + desc + " -> %r" % (got,))
    if not ok:
        fails.append(desc)

def make_panel(guard: bool):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content.setMinimumHeight(2000)
    lay = QVBoxLayout(content)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(50)
    combo = QComboBox()
    for i in range(6):
        combo.addItem("字体 %d" % i)
    combo.setCurrentIndex(2)
    lay.addWidget(slider)
    lay.addWidget(combo)
    lay.addStretch(1)
    scroll.setWidget(content)
    scroll.resize(400, 300)
    scroll.show()
    app.processEvents()
    if guard:
        g = WheelToScroll(scroll)
        for w in content.findChildren(QSlider) + content.findChildren(QComboBox):
            w.installEventFilter(g)
    return scroll, slider, combo

def wheel(widget, dy=-120, pixels=0):
    ev = QWheelEvent(QPointF(8, 8), QPointF(8, 8),
                     QPoint(0, pixels), QPoint(0, dy),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)
    app.processEvents()

# ---- 1) 对照组：不装守卫，滚轮会改值（证明这个测试确实能抓到 bug） ----
s0, sl0, cb0 = make_panel(False)
wheel(sl0, -120)
wheel(cb0, -120)
print("== 对照组（未装守卫）==")
chk("QSlider 滚轮改值（复现原 bug）", sl0.value() != 50, True)
chk("QComboBox 滚轮改索引（复现原 bug）", cb0.currentIndex() != 2, True)

# ---- 2) 装守卫：值不变，页面滚动 ----
scroll, slider, combo = make_panel(True)
sb = scroll.verticalScrollBar()
start = sb.value()
before_sl, before_cb = slider.value(), combo.currentIndex()
wheel(slider, -120)
wheel(combo, -120)
print("== 装守卫后 ==")
chk("字体下拉框索引不变", combo.currentIndex(), before_cb)
chk("透明度滑条值不变", slider.value(), before_sl)
chk("滚动条确实向下移动", sb.value() > start, True)
after_down = sb.value()
wheel(slider, 120)   # 反向滚
chk("反向滚轮能滚回去", sb.value() < after_down, True)
chk("反向滚轮后滑条值仍不变", slider.value(), before_sl)

# 精确式触控板：部分驱动只给 pixelDelta（angleDelta=0），
# QScrollBar::wheelEvent 不认它，守卫必须按像素补滚，否则页面滑不动。
sb.setValue(sb.minimum())
px0 = sb.value()
wheel(combo, 0, pixels=-60)
chk("pixelDelta 不改值", (slider.value(), combo.currentIndex()),
    (before_sl, before_cb))
chk("pixelDelta 仍能滚动页面", sb.value() > px0, True)

# ---- 3) 非滚轮事件不受影响（过滤器必须放行） ----
from PySide6.QtCore import QEvent as _QE
_probe = WheelToScroll(scroll)
chk("非滚轮事件放行（返回 False）",
    _probe.eventFilter(slider, _QE(_QE.Type.MouseButtonPress)), False)

# ---- 4) 拖动/程序设值仍可用（守卫只拦 Wheel） ----
slider.setValue(77)
chk("程序设值不受影响", slider.value(), 77)
combo.setCurrentIndex(4)
chk("程序切换字体不受影响", combo.currentIndex(), 4)

print()
if fails:
    print("FAILED:", fails)
    sys.exit(1)
print("ALL PASS")
