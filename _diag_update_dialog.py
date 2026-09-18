# -*- coding: utf-8 -*-
"""离屏渲染 UpdateDialog：确认蓝奏云/GitHub 双按钮与免安装版链接都正常出现。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lyrics_overlay as L  # noqa: E402

app = QApplication.instance() or QApplication([])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview")


def shoot(name, info):
    dlg = L.UpdateDialog(None, info)
    pm = dlg.grab()
    path = os.path.join(OUT, name)
    pm.save(path)
    btns = [b.text() for b in dlg.findChildren(L.QPushButton)]
    links = [lbl.text() for lbl in dlg.findChildren(L.QLabel)
             if lbl.objectName() == "udlink"]
    ok = os.path.getsize(path) > 2000
    print(("  PASS  " if ok else "  FAIL  ") + "%s  按钮=%s  链接=%s  尺寸=%dx%d"
          % (name, btns, links, pm.width(), pm.height()))
    return ok


r = []
r.append(shoot("update_dlg_lanzou.png", {
    "version": "1.1.0", "url": "https://github.com/xiaohao8/Desktop-sing/releases/latest",
    "lanzou_setup": "https://wwbgk.lanzouu.com/iTgxJ48z9kjg",
    "lanzou_portable": "https://wwbgk.lanzouu.com/ih2SA48z8rmf",
    "notes": "1. 新增蓝奏云更新源\n2. 修复若干显示问题\n3. 优化启动速度"}))
r.append(shoot("update_dlg_github.png", {
    "version": "1.1.0", "url": "https://github.com/xiaohao8/Desktop-sing/releases/latest",
    "notes": "仅 GitHub 直链（镜像表未收录该版本）"}))
r.append(shoot("update_dlg_portable.png", {
    "version": "1.2.0", "url": "", "lanzou_portable": "https://wwbgk.lanzouu.com/ih2SA48z8rmf",
    "notes": "只有免安装版镜像"}))

print("\n合计 %d 项，失败 %d 项" % (len(r), len([x for x in r if not x])))
sys.exit(0 if all(r) else 1)
