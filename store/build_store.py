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
SHORT_NAME = "桌面歌词"        # 磁贴底部短名称（全名过长会被截断）
PUBLISHER_DISPLAY_NAME = "Desktop-sing Project"

# 清单里的 Description（uap:VisualElements/@Description）：
# 商店策略 10.1.1 要求准确描述「重要限制」。这里把限制写全，
# 免得审核员按描述预期去测却发现对不上。
#
# ⚠️ 这一串会被写进用户可见的清单，**同样受 10.1.1 / 11.2 约束**：
#    不点名任何第三方品牌（旧版写了「如 QQ音乐 / 网易云音乐 / 酷狗音乐」，
#    等于把商标写进包元数据）。要说明兼容性就描述「接入 SMTC」这一客观事实。
DESCRIPTION = ("常驻桌面的卡拉OK歌词悬浮条：自动跟随接入 Windows 系统媒体控制（SMTC）"
               "的播放器显示逐字歌词。"
               "支持 5 种悬浮样式、4 种氛围屏保、封面主色换肤、翻译与音译显示、进度时间、"
               "全局快捷键（默认关闭）与开机自启（默认关闭）。"
               "所有数据仅保存在本机，无账号、无广告、无追踪。")

# 商店商品页「描述」字段（比清单 Description 长，可分段）。
# 受 10.1.1（准确描述重要限制）与 10.7（本地化：界面只有中文需如实说明）约束。
#
# ⚠️ 功能数量必须与代码一致，且与主程序「关于」窗口、官网口径统一。
#    真源：STYLE_NAMES(5) / ANIM_STYLES(9) / saver_style(4) / POSITION_PRESETS(7)。
#    写数字前先数一遍，别凭印象——数字对不上审核员会当成虚假描述。
STORE_LISTING_DESCRIPTION = """桌面歌词是一款常驻桌面的歌词悬浮条：你在播放器里播放歌曲，它就把逐字卡拉OK歌词显示在桌面上，不挡视线、不用切窗口。

【主要功能】
· 逐字卡拉OK歌词：多源并行获取（QQ音乐 / 网易云音乐 / 酷狗音乐 / LRCLIB），择优显示
· 5 种悬浮样式 · 9 种逐字动画 · 柔和描边（浅色深色壁纸都清晰）
· 4 种氛围屏保（3D 粒子 / 极简时钟 / 音浪 / 星轨）：长时间空闲自动进入黑底防烧屏画面
· 封面主色换肤 · 翻译与音译歌词 · 进度时间
· 摆放位置预设（7 个锚点，换分辨率也贴边）· 可锁定位置防误拖
· 全局快捷键（默认关闭，可在设置里开启）
· 开机自启（默认关闭，可在系统「设置 → 应用 → 启动」里开启）

【使用前提（重要限制）】
· 仅支持 Windows 10（1809 及以上）/ Windows 11，仅 x64
· 歌词信息来自 Windows 系统媒体控制（SMTC）：播放器必须接入 SMTC 才能读取当前歌曲，VR 类或老式播放器可能读不到
· 同时打开多个播放器时，跟随正在播放的那一个
· 需要联网才能获取歌词；已获取的歌词会缓存在本机，断网时可继续显示
· 界面与歌词界面目前仅有简体中文

【隐私】
程序没有账号系统、没有广告、没有统计埋点，不收集任何个人身份信息。设置、歌词缓存与日志全部保存在本机 %APPDATA%\\Desktop-sing\\ 目录，不上传任何服务器。仅在获取歌词时按需向上述音乐平台的公开接口发送歌曲名 / 歌手名 / 时长。

【关于更新】
Microsoft Store 版本由商店统一分发更新，程序内不含任何自更新通道。"""

# 提审时填「受限功能说明」用（runFullTrust）。Partner Center 该字段长度有限，
# 长文案会被静默截断，所以这里只给两句。
RUNFULLTRUST_STATEMENT = (
    "本应用是 Win32 桌面程序（PySide6 打包），需要读取 Windows 系统媒体控制"
    "（SMTC）提供的当前播放信息、在无边框透明窗口上绘制歌词，并使用全局快捷键、"
    "系统托盘与开机自启项，这些必须运行在完全信任模式下。"
    "应用不修改系统文件，不安装其他软件，所有数据仅保存在本机用户目录。")

# 提审时填「认证说明」（Notes for certification）。帮审核员知道怎么测。
CERTIFICATION_NOTES = """测试指引（桌面歌词 v{version}）
1. 本应用无账号、无需登录，安装后直接可用。
2. 【怎么打开设置】右键点击系统托盘图标 → 菜单选「设置…」。
   注意：全局快捷键默认是关闭的（避免与其他软件抢键），所以 Ctrl+Alt+S
   在初始状态下无效，请不要据此判断功能异常；若想用快捷键，
   先在设置面板里打开「全局快捷键」开关。
3. 【怎么看歌词】核心功能需要播放器配合：用 Windows 自带的「媒体播放器」
   或任意接入 Windows 系统媒体控制（SMTC）的播放器播放一首歌，
   歌词会自动出现在屏幕底部的悬浮条上。若手边没有播放器，
   可用系统「媒体播放器」打开任意本地音频文件。
   本应用不读取音乐文件本身，只读取系统媒体控制提供的曲目信息。
4. 歌词抓取需要联网（访问音乐平台的公开歌词接口）。断网时不会崩溃，
   浮层会显示「纯音乐或暂无歌词」，已缓存的歌词仍可正常显示。
5. 浮层初始位于屏幕底部中央；鼠标拖动可改变位置，右键菜单可锁定位置。
6. 全部快捷键（需先在设置里开启）：Ctrl+Alt+P 播放暂停 · Ctrl+Alt+, / .
   上下首 · Ctrl+Alt+[ / ] 歌词偏移 · Ctrl+Alt+L 显示隐藏 · Ctrl+Alt+S 设置
   · Ctrl+Alt+T 样式 · Ctrl+Alt+D 显示模式 · Ctrl+Alt+G 锁定 · Ctrl+Alt+B 屏保。
7. 商店版本说明：程序内没有更新检查（更新由 Microsoft Store 分发）；
   「开机自启」默认关闭，在系统「设置 → 应用 → 启动」里开启，
   也可在任务管理器的「启动应用」标签开关。
8. 若歌词未出现，最常见原因是播放器未接入 SMTC（本应用读不到曲目信息），
   属预期行为，不是崩溃或功能缺失。"""

# 商店版不要带的文件（卸载器没有意义：商店应用从系统设置里卸载）
EXCLUDE_FILES = {"卸载桌面歌词.bat"}

# 必须随包分发的许可/声明文件。
# 为什么不能只放在仓库里：Apache-2.0 第 4 条要求「向接收者提供一份 NOTICE」，
# 内置的 MiSans 也要求保留许可说明。商店用户只拿到 .msix，看不到 GitHub 仓库，
# 所以这些文件必须真的进包，否则是实打实的许可违规。
# （来源：仓库根目录，打包时复制到程序目录，用户可在安装目录里查看。）
#
# 中英各一份：Microsoft Store 是全球分发的，商店页/审核语言可能是英文，
# 只给中文声明等于英文用户拿不到可读的隐私说明。
# 使用说明也一并带上：MSIX 的布局来自 onedir，而 onedir 里**没有**使用说明，
# 早先只有便携版/安装版才有 → 商店用户装完找不到任何使用说明，两条渠道不一致。
BUNDLED_LICENSES = ("LICENSE-THIRD-PARTY.txt", "PRIVACY.md",
                    "使用说明.txt", "PRIVACY.en.md", "USAGE.en.txt")


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

    # 许可与隐私声明必须随包（见 BUNDLED_LICENSES 注释）
    for f in BUNDLED_LICENSES:
        src = os.path.join(ROOT, f)
        if not os.path.isfile(src):
            raise SystemExit("缺少随包声明文件：%s（许可合规要求，不能省）" % f)
        shutil.copyfile(src, os.path.join(app_dir, f))
        print("  [声明] 已随包 %s" % f)
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
              .replace("{{SHORT_NAME}}", SHORT_NAME)
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
    """出包后的自检：结构完整 + 关键文件都在 + 清单引用资产齐全 + 大小合理。"""
    import re
    import zipfile
    ok = True
    with zipfile.ZipFile(msix_path) as z:
        names = z.namelist()
        nameset = set(names)
        must = ["AppxManifest.xml", "Assets/StoreLogo.png",
                "Assets/Square150x150Logo.png", "Assets/Square44x44Logo.png",
                "Assets/Square71x71Logo.png", "Assets/Square310x310Logo.png",
                "Assets/Wide310x150Logo.png",
                "Desktop-sing/Desktop-sing.exe"]
        for m in must:
            if m not in nameset:
                print("  [FAIL] 包里缺 %s" % m)
                ok = False
        if "Desktop-sing/卸载桌面歌词.bat" in nameset:
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

        # 清单里引用的每个资产都必须真的在包里（商店最常见的静态拒审原因）
        refs = set(re.findall(r'Assets\\([A-Za-z0-9._\-]+\.png)', mf))
        missing = sorted(r for r in refs if ("Assets/" + r) not in nameset)
        if missing:
            print("  [FAIL] 清单引用了但包里没有的资产：%s" % ", ".join(missing))
            ok = False
        else:
            print("  [OK] 清单引用的 %d 个资产全部就位" % len(refs))
        # 宣称支持「多档缩放」的关键资产要有 scale-400（官方建议 100/200/400）
        for base in ("Square44x44Logo", "Square150x150Logo"):
            if "Assets/%s.scale-400.png" % base not in nameset:
                print("  [FAIL] %s 缺 scale-400 变体" % base)
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


def export_listing(version: str) -> str:
    """把提审要往上贴的文案导出成一个 Markdown，免得到时手忙脚乱。

    Partner Center 各字段是分散的表单，这里按「字段名 → 内容」整理，
    复制粘贴即可。文件落在 store/out/listing-v<ver>.md。
    """
    os.makedirs(OUTDIR, exist_ok=True)
    pkgver = package_version(version)     # MSIX 文件名里是四段版本
    path = os.path.join(OUTDIR, "listing-v%s.md" % version)
    txt = f"""# 桌面歌词 微软商店提审材料（v{version}）

> 由 `store/build_store.py --listing` 自动生成，内容取自 build_store.py 的常量，
> 改文案请改常量后重新生成，别直接编辑本文件。

## 1. 程序包
`store/out/Desktop-sing-{pkgver}-x64.msix`（**未签名**，商店会重签）

> 每次提交版本号必须递增；版本号来自 `lyrics_overlay.py` 的 `APP_VERSION`，
> 会自动补成四段（{pkgver}）。

## 2. 属性 / 类别
- 产品类别：**音乐（Music）**；次级建议：实用工具（Utilities）
- 支持设备：PC（Windows 10 1809+ / Windows 11，x64）
- 语言：**简体中文**（声明几种就要本地化几种描述的文本）

## 3. 商品页「描述」
```
{STORE_LISTING_DESCRIPTION}
```

## 4. 搜索词（≤ 7 个，不得含价格词、不得用他人品牌名）
`桌面歌词、歌词、悬浮歌词、卡拉OK、逐字歌词、桌面工具、音乐`

## 5. 版本说明（首次提交留空）
首次提交留空即可。

## 6. 受限功能说明（runFullTrust）★ 必填，别贴长的
Partner Center 提示「需要请求批准才能使用受限功能 runFullTrust」，这是正常预警。
在该字段填下面这**两句话**（字段有长度限制，长文案会被静默截断）：
```
{RUNFULLTRUST_STATEMENT}
```

## 7. 认证说明（Notes for certification）
```
{CERTIFICATION_NOTES.format(version=version)}
```

## 8. 隐私政策 URL（必填）
`https://<你的域名>/privacy.html`
（对应仓库 `site/privacy.html`，发布官网后把真实 URL 填进来。
 商店策略 10.5.1 特别点名：Desktop Bridge 与 Win32 产品**必须**始终具备隐私政策。）

## 9. 截图（至少 1 张，建议 1366×768 及以上）
需人工用运行中的程序截图。建议拍这几张：
1. 歌词浮层在桌面底部的实际效果（含封面与逐字高亮）；
2. 设置面板（体现功能丰富度）；
3. 氛围屏保效果；
4. 托盘菜单。
⚠️ 截图里不要出现第三方播放器的受版权保护的界面素材（用纯色壁纸 + 本程序窗口）。

## 10. 年龄分级（IARC 问卷）
按实填写：无用户生成内容、无社交、无付费、无暴力色情内容 →
通常得到 PEGI 3 / ESRB Everyone / 中国「全年龄」。

## 11. 提交选项
建议选「认证通过后尽快发布」以便发现问题及时处理。

## 12. 提交前的自检命令
```bash
.buildenv\\Scripts\\python.exe store\\audit_round3.py     # 商店模式离线自检 + 材料完整性
.buildenv\\Scripts\\python.exe store\\build_store.py --fresh   # 全量重打包
```
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="先重跑 build_exe.py --dir")
    ap.add_argument("--name", default="", help="Partner Center 的包标识名")
    ap.add_argument("--publisher", default="", help="Partner Center 的发布者 CN=…")
    ap.add_argument("--version", default="", help="覆盖版本号（默认取 APP_VERSION）")
    ap.add_argument("--wack", action="store_true", help="打完包跑 WACK 认证")
    ap.add_argument("--listing", action="store_true",
                    help="只导出提审文案（store/out/listing-v*.md），不打 MSIX")
    args = ap.parse_args()

    if args.listing:
        ver = args.version or app_version()
        p = export_listing(ver)
        print("[提审材料] %s" % p)
        return

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
