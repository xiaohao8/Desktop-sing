# -*- coding: utf-8 -*-
"""把 dist/Desktop-sing-v1.0.0/ 打成免安装极速版 zip，顶层目录为 Desktop-sing-v1.0.0。"""
import os
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "dist", "Desktop-sing-v1.0.0")
OUT = os.path.join(BASE, "dist", "release", "桌面歌词-v1.0.0-免安装极速版.zip")
TOP = "Desktop-sing-v1.0.0"

if not os.path.isdir(SRC):
    raise SystemExit("源目录不存在: %s" % SRC)
if os.path.isfile(OUT):
    os.remove(OUT)

n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, _, fs in os.walk(SRC):
        for f in fs:
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, SRC)
            z.write(full, os.path.join(TOP, rel))
            n += 1
    # 便携版随包附带说明文档（与安装版 SEC_CORE 一致）。
    # 卸载脚本 卸载桌面歌词.bat 已由 build_exe.py 复制进 onedir 源目录，os.walk 已包含，
    # 这里不再重复写入，避免 zip 内同名冲突。
    docs = [("使用说明.txt", "使用说明.txt"),
            ("隐私声明.txt", "PRIVACY.md")]
    for arcname, srcname in docs:
        sp = os.path.join(BASE, srcname)
        if os.path.isfile(sp):
            z.write(sp, os.path.join(TOP, arcname))
            n += 1
print("[完成] %s  (%d 个文件, %.1f MB)"
      % (OUT, n, os.path.getsize(OUT) / 1048576.0))
