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
    #
    # ⚠️ LICENSE-THIRD-PARTY.txt 是**许可合规要求**，不能只在仓库里放一份：
    #    Apache-2.0 第 4 条要求向接收者提供 NOTICE，内置 MiSans 也要求保留许可说明。
    #    用户拿到的是 zip，看不到 GitHub 仓库，所以必须真的打进去。
    #
    # 文档中英各一份：商店是全球分发的，英文用户拿到 zip 后要能看到英文的隐私声明与使用说明。
    # 文件名用 ASCII（-EN 后缀）而不是 "隐私声明(EN).txt"，避免跨平台解压时的编码问题。
    docs = [("使用说明.txt", "使用说明.txt"),
            ("隐私声明.txt", "PRIVACY.md"),
            ("第三方许可.txt", "LICENSE-THIRD-PARTY.txt"),
            ("Usage-EN.txt", "USAGE.en.txt"),
            ("Privacy-EN.txt", "PRIVACY.en.md")]
    for arcname, srcname in docs:
        sp = os.path.join(BASE, srcname)
        if os.path.isfile(sp):
            z.write(sp, os.path.join(TOP, arcname))
            n += 1
print("[完成] %s  (%d 个文件, %.1f MB)"
      % (OUT, n, os.path.getsize(OUT) / 1048576.0))
