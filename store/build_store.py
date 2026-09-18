# -*- coding: utf-8 -*-
"""把 PyInstaller onedir 产物打成 Microsoft Store 用的 MSIX 包。

    .buildenv\\Scripts\\python.exe store\\build_store.py                # 用现有 dist 产物打包
    .buildenv\\Scripts\\python.exe store\\build_store.py --fresh        # 先重跑 build_exe --dir 再打包
    .buildenv\\Scripts\\python.exe store\\build_store.py --wack         # 打完顺带跑 WACK（需管理员）

包标识（Identity Name / Publisher）必须来自 Partner Center，读三处、优先级从高到低：
    1) 命令行 --name / --publisher
    2) store/identity.local.json      （本机填一次即可，勿提交仓库）
    3) 占位值                          （能出包，仅供本地看结构，**不能上传**）

输出：store/out/Desktop-sing-<版本>-x64.msix（未签名——Store 提审就传未签名包，
      微软会用它自己的证书重签；本地自签测试见 README-STORE.md）。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
ONEDIR = os.path.join(ROOT, "dist", "Desktop-sing-v1.0.0")
LAYOUT = os.path.join(BASE, "build", "layout")
OUTDIR = os.path.join(BASE, "out")
TEMPLATE = os.path.join(BASE, "AppxManifest.template.xml")
IDENTITY_LOCAL = os.path.join(BASE, "identity.local.json")

MAKEAPPX = r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe"
WACK = r"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe"

DISPLAY_NAME = "桌面歌词"
PUBLISHER_DISPLAY_NAME = "Desktop-sing Project"
DESCRIPTION = ("常驻桌面的卡拉OK歌词悬浮条：跟随 QQ音乐 / 网易云音乐 / 酷狗音乐等"
               "接入系统媒体栏的播放器自动显示逐字歌词。支持氛围屏保、封面主色换肤、"
               "翻译与音译显示、进度时间、全局快捷键与开机自启。所有数据仅保存在本机。")

# 商店版不要带的文件（卸载器没有意义：商店应用从系统设置里卸载）
EXCLUDE_FILES = {"卸载桌面歌词.bat"}


def app_version() -> str:
    """从主程序读 APP_VERSION（省得两处维护）。"""
    txt = open(os.path.join(ROOT, "lyrics_overlay.py"), encoding="utf-8").read()
    for line in txt.splitlines():
        if line.startswith("APP_VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("lyrics_overlay.py 里没找到 APP_VERSION")


def package_version(v: str) -> str:
    """MSIX 版本必须是 4 段数字（1.0.0 → 1.0.0.0）。"""
    parts = [p for p in v.strip().split(".") if p != ""]
    if len(parts) > 4:
        parts = parts[:4]
    while len(parts) < 4:
        parts.append("0")
    if not all(p.isdigit() for p in parts):
        raise SystemExit("版本号只能是数字：%s" % v)
    return ".".join(parts)


def load_identity(args):
    """按 命令行 → identity.local.json → 占位 的优先级取标识。"""
    name, publisher = args.name, args.publisher
    if (not name or not publisher) and os.path.isfile(IDENTITY_LOCAL):
        try:
            cfg = json.load(open(IDENTITY_LOCAL, encoding="utf-8"))
            name = name or cfg.get("name", "")
            publisher = publisher or cfg.get("publisher", "")
        except Exception as ex:
            print("[警告] identity.local.json 解析失败：%s" % ex)
    name = name or "Desktop-sing-PLACEHOLDER"
    publisher = publisher or "CN=PLACEHOLDER-FILL-ME"
    return name, publisher


def stage_layout():
    """组装 MSIX 布局：清单 + 资产 + onedir 程序本体（去掉商店版不该带的文件）。"""
    if not os.path.isdir(ONEDIR):
        raise SystemExit("没找到 %s —— 先跑 build_exe.py --dir，或加 --fresh" % ONEDIR)
    # 布局目录每次重建。沙箱会拦批量删除，用「改名归档」代替 rm -rf
    if os.path.isdir(LAYOUT):
        os.rename(LAYOUT, LAYOUT + ".old-%d" % int(os.path.getmtime(LAYOUT)))
    app_dir = os.path.join(LAYOUT, "Desktop-sing")
    os.makedirs(app_dir, exist_ok=True)
    shutil.copytree(ONEDIR, app_dir, dirs_exist_ok=True)
    for f in EXCLUDE_FILES:
        p = os.path.join(app_dir, f)
        if os.path.isfile(p):
            os.remove(p)
    assets_dst = os.path.join(LAYOUT, "Assets")
    os.makedirs(assets_dst, exist_ok=True)
    import make_store_assets
    src_assets = os.path.join(BASE, "assets")
    if not os.path.isdir(src_assets) or not make_store_assets.verify(src_assets):
        print("[资产] 缺失或尺寸不对，重新生成…")
        make_store_assets.generate()
    for name in os.listdir(src_assets):
        shutil.copyfile(os.path.join(src_assets, name), os.path.join(assets_dst, name))
    return LAYOUT


def write_manifest(name: str, publisher: str, version: str) -> str:
    tpl = open(TEMPLATE, encoding="utf-8").read()
    out = (tpl.replace("{{IDENTITY_NAME}}", name)
              .replace("{{PUBLISHER}}", publisher)
              .replace("{{VERSION}}", version)
              .replace("{{DISPLAY_NAME}}", DISPLAY_NAME)
              .replace("{{PUBLISHER_DISPLAY_NAME}}", PUBLISHER_DISPLAY_NAME)
              .replace("{{DESCRIPTION}}", DESCRIPTION))
    # 模板注释里有「{{占位符}}」之类的说明文字，发布清单不需要它们——
    # 剥掉全部 XML 注释，顺带把多出来的空行收干净
    out = re.sub(r"<!--.*?-->", "", out, flags=re.S)
    out = re.sub(r"\n\s*\n+", "\n\n", out).strip() + "\n"
    path = os.path.join(LAYOUT, "AppxManifest.xml")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(out)
    return path


def run_makeappx(msix_path: str) -> bool:
    cmd = [MAKEAPPX, "pack", "/d", LAYOUT, "/p", msix_path, "/v"]
    print("[打包] %s" % " ".join(cmd[:6]) + " …")
    r = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    out = (r.stdout or "") + (r.stderr or "")
    # /v 的逐文件日志没价值，只看错误/警告和结果行
    # （带冒号才匹配——否则 api-ms-win-core-errorhandling 这类 DLL 名会误中）
    keys = ("error:", "Error:", "ERROR:", "warning:", "Warning:", "Package creation")
    for l in out.splitlines():
        if any(k in l for k in keys):
            print("   " + l)
    if r.returncode != 0:
        print(out[-1500:])
        return False
    return True


def verify_msix(msix_path: str, identity_is_placeholder: bool) -> bool:
    """出包后的自检：结构完整 + 关键文件都在 + 大小合理。"""
    import zipfile
    ok = True
    with zipfile.ZipFile(msix_path) as z:
        names = z.namelist()
        must = ["AppxManifest.xml", "Assets/StoreLogo.png",
                "Assets/Square150x150Logo.png", "Assets/Square44x44Logo.png",
                "Desktop-sing/Desktop-sing.exe"]
        for m in must:
            if m not in names:
                print("  [FAIL] 包里缺 %s" % m)
                ok = False
        if "Desktop-sing/卸载桌面歌词.bat" in names:
            print("  [FAIL] 商店包里不该有卸载脚本")
            ok = False
        mf = z.read("AppxManifest.xml").decode("utf-8")
        for bad in ("{{", "}}"):
            if bad in mf:
                print("  [FAIL] 清单里有未替换的模板占位符（%s）" % bad)
                ok = False
        if "PLACEHOLDER" in mf:
            if identity_is_placeholder:
                print("  [警告] 占位标识（预期，仅供本地看结构，不能上传）")
            else:
                print("  [FAIL] 已填真实标识但清单里仍有 PLACEHOLDER 残留")
                ok = False
        print("  [OK] 包内 %d 个文件，%.1f MB" % (len(names), os.path.getsize(msix_path) / 1048576))
    return ok


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_wack(msix_path: str):
    if not os.path.isfile(WACK):
        print("[WACK] 本机没装 App Certification Kit，跳过（提交前建议装上跑一次）")
        return
    print("[WACK] 运行认证测试（需要管理员权限，可能要几分钟）…")
    r = subprocess.run([WACK, "test", "-apptype", "msix", "-package", msix_path],
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-1500:] if out.strip() else "[WACK] 无输出，退出码 %d" % r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="先重跑 build_exe.py --dir")
    ap.add_argument("--name", default="", help="Partner Center 的包标识名")
    ap.add_argument("--publisher", default="", help="Partner Center 的发布者 CN=…")
    ap.add_argument("--version", default="", help="覆盖版本号（默认取 APP_VERSION）")
    ap.add_argument("--wack", action="store_true", help="打完包跑 WACK 认证")
    args = ap.parse_args()

    sys.path.insert(0, BASE)

    if args.fresh:
        print("[构建] 先跑 build_exe.py --dir …")
        r = subprocess.run([os.path.join(ROOT, ".buildenv", "Scripts", "python.exe"),
                            "-u", os.path.join(ROOT, "build_exe.py"), "--dir"],
                           cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit("build_exe.py 失败（退出码 %d）" % r.returncode)

    ver = package_version(args.version or app_version())
    name, publisher = load_identity(args)
    identity_is_placeholder = "PLACEHOLDER" in (name + publisher)

    print("== 桌面歌词 MSIX 打包 ==")
    print("版本   : %s" % ver)
    print("标识   : %s" % name)
    print("发布者 : %s" % publisher)

    stage_layout()
    write_manifest(name, publisher, ver)

    os.makedirs(OUTDIR, exist_ok=True)
    msix = os.path.join(OUTDIR, "Desktop-sing-%s-x64.msix" % ver)
    if os.path.isfile(msix):
        os.remove(msix)
    if not run_makeappx(msix):
        raise SystemExit("makeappx 打包失败")
    if not verify_msix(msix, identity_is_placeholder):
        raise SystemExit("包自检未通过")

    print("\n[完成] %s" % msix)
    print("       SHA256 = %s" % sha256(msix))
    if identity_is_placeholder:
        print("       ⚠️ 当前是占位标识：上传前必须填真实 Identity（见 README-STORE.md）")
    if args.wack:
        run_wack(msix)


if __name__ == "__main__":
    main()
