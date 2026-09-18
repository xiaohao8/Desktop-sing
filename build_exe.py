# -*- coding: utf-8 -*-
"""把桌面歌词打包成单文件 exe。

Qt6 / PySide6 需要 PyInstaller 5+（本机系统 Python 自带的是 3.6，太旧），
所以请先建一次带 --system-site-packages 的构建虚拟环境（继承系统 PySide6，不污染系统环境）：

    python -m venv .buildenv --system-site-packages
    .buildenv\\Scripts\\python.exe -m pip install -U "pyinstaller>=6"

之后每次发版只需：
    .buildenv\\Scripts\\python.exe build_exe.py            # 精简（默认）
    .buildenv\\Scripts\\python.exe build_exe.py --full     # 带全部内置字体
    .buildenv\\Scripts\\python.exe build_exe.py --no-font  # 不内置字体，体积最小
    .buildenv\\Scripts\\python.exe build_exe.py --dir      # 产出 onedir 目录版（启动更快）

产物：dist/Desktop-sing-v<版本号>.exe

体积优化要点（2.4.4 起，72.8MB → 40.6MB）：
  · winsdk 精准收集：--collect-all winsdk 会把整个 SDK 拉进来，这里只收 5 个子模块；
  · 排除用不到的 Qt 模块：opengl32sw（19.7MB 软件渲染）、QtQml/Quick/Pdf/OpenGL/Svg 等；
  · 排除 Qt 的 OpenSSL 3（libcrypto-3-x64 + libssl-3-x64 + qopensslbackend）：本项目
    HTTP 全走 urllib（用 Python 自带的 OpenSSL 1.1），QtNetwork 只用来做 QLocalServer
    单实例 IPC，用不到 TLS；
  · 排除 setuptools / pkg_resources / pycparser 等被间接拖进来的打包期依赖；
  · 内置字体只带 MiSans-Regular（粗体由 Qt 合成），需要全字重的用 --full。

各项占用（单文件 exe 内部实际压缩后大小，用 _diag_exe_size.py 量的）：
  winsdk/_winrt.pyd 10.6MB | Qt6Gui 3.75 | MiSans 5.18 | Qt6Widgets 2.81 | Qt6Core 2.63
  QtWidgets.pyd 1.82 | python38 1.78 | QtGui.pyd 1.31 | libcrypto-1_1 1.24 | PYZ 1.55

还能不能再小？（2026-09 实测结论，别再走弯路）
  · _winrt.pyd 10.6MB：winsdk 的投影是**单个**大 .pyd，少收子模块也省不掉它。
    换成 winrt-* 细分命名空间包能降到两三 MB，但那些包要求 Python ≥ 3.9，
    本机运行时就 3.8.6 —— 不升级 Python 就没得谈。
  · MiSans 5.18MB：**不要做 GB2312 子集**。实测子集(6763 汉字)能把字体从 7.75MB
    压到 1.65MB，但缺字时 Qt 不会回退到系统字体，而是**一个像素都不画** ——
    歌词里的生僻字（如「龘」）会直接凭空消失，比出豆腐块还糟。
    所以只有两个选项：整个带上（默认），或者 --no-font 整个不带。
  · 保留全部字形、只丢 GPOS/GSUB 等布局表：只省 0.47MB，却会伤到拉丁文的字距
    连字，不划算，未采用。
"""
import os
import re
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "lyrics_overlay.py")
NAME = "Desktop-sing"

# 只用得到的 Windows SDK 子模块（--collect-all winsdk 会把整个 SDK 40+MB 全拉进来）
WINSDK_NEEDED = [
    "winsdk.windows.media.control",
    "winsdk.windows.storage.streams",
    "winsdk.windows.foundation",
    "winsdk.windows.foundation.collections",
    "winsdk.windows.storage",
]

# 用不到的 Qt 模块（省下 opengl32sw 19.7MB + QtQml/Quick/Pdf/OpenGL/Svg 等约 20MB）
QT_EXCLUDE = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuickControls2",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtVirtualKeyboard", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtTest", "PySide6.QtUiTools", "PySide6.QtPrintSupport",
    "PySide6.QtSql", "PySide6.QtConcurrent", "PySide6.QtScxml",
    "PySide6.QtStateMachine", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
]

# 用不到的 Qt 二进制（按文件名后缀筛）：软件渲染器 opengl32sw 19.7MB 是最大单项；
# Qml/Quick/Pdf/OpenGL/Svg/VirtualKeyboard 都是我们完全不碰的模块。
QT_DROP_DLL = (
    "opengl32sw.dll",
    "Qt6Quick.dll", "Qt6QuickControls2.dll", "Qt6QuickWidgets.dll", "Qt6Quick3D.dll",
    "Qt6Quick3DCore.dll", "Qt6Quick3DRender.dll", "Qt6Quick3DUtils.dll", "Qt6Quick3DAssetImport.dll",
    "Qt6QuickShapes.dll", "Qt6QuickParticles.dll", "Qt6QuickEffects.dll", "Qt6QuickLayouts.dll",
    "Qt6Qml.dll", "Qt6QmlModels.dll", "Qt6QmlCore.dll", "Qt6QmlWorkerScript.dll", "Qt6QmlNetwork.dll",
    "Qt6QmlXmlListModel.dll", "Qt6QmlLocalStorage.dll", "Qt6QmlCompiler.dll", "Qt6QmlMeta.dll",
    "Qt6Pdf.dll", "Qt6PdfWidgets.dll", "Qt6PdfQuick.dll",
    "Qt6OpenGL.dll", "Qt6OpenGLWidgets.dll", "Qt6Svg.dll", "Qt6SvgWidgets.dll",
    "Qt6VirtualKeyboard.dll", "Qt6Charts.dll", "Qt6ChartsQml.dll", "Qt6DataVisualization.dll",
    "Qt6DataVisualizationQml.dll", "Qt6Multimedia.dll", "Qt6MultimediaWidgets.dll",
    "Qt6MultimediaQuick.dll", "Qt6WebEngineCore.dll", "Qt6WebEngineWidgets.dll", "Qt6WebEngineQuick.dll",
    "Qt6WebSockets.dll", "Qt6WebChannel.dll", "Qt63DCore.dll", "Qt63DRender.dll", "Qt63DInput.dll",
    "Qt63DLogic.dll", "Qt63DAnimation.dll", "Qt63DExtras.dll", "Qt63DQuick.dll",
    "Qt6Sql.dll", "Qt6Test.dll", "Qt6Designer.dll", "Qt6Help.dll", "Qt6PrintSupport.dll",
    "Qt6Concurrent.dll", "Qt6Scxml.dll", "Qt6StateMachine.dll", "Qt6SpatialAudio.dll",
    "Qt6TextToSpeech.dll", "Qt6SerialPort.dll", "Qt6ShaderTools.dll", "Qt6DBus.dll",
    "Qt6Nfc.dll", "Qt6Positioning.dll", "Qt6PositioningQuick.dll", "Qt6RemoteObjects.dll",
    "Qt6Sensors.dll", "Qt6Bluetooth.dll", "Qt6Bodymovin.dll", "Qt6 Labs*.dll",
    # Qt 的 OpenSSL 3：本项目 HTTP 走 urllib（Python 自带 OpenSSL 1.1），
    # QtNetwork 只用来起 QLocalServer 做单实例 IPC，不需要 TLS 后端。
    "libcrypto-3-x64.dll", "libssl-3-x64.dll",
)
# 平台插件只留 qwindows（Windows 原生）；图像格式留常用的 jpeg/png/gif/webp；
# imageformats 里其余的、以及全部 Qt 自带翻译（我们不用 QTranslator）都不要。
QT_DROP_PLUGIN = (
    "platforms/qdirect2d.dll", "platforms/qminimal.dll", "platforms/qoffscreen.dll",
    "imageformats/qtiff.dll", "imageformats/qicns.dll", "imageformats/qico.dll",
    "imageformats/qtga.dll", "imageformats/qwbmp.dll", "imageformats/qpdf.dll",
    "imageformats/qsvg.dll", "iconengines/qsvgicon.dll",
    "virtualkeyboard/qtvirtualkeyboardplugin.dll",
    "tls/qopensslbackend.dll",        # 走 urllib，不做 Qt 的 HTTPS
)

# 被 hook 间接拖进来的打包期依赖（运行时用不到）
PKG_EXCLUDE = [
    "setuptools", "pkg_resources", "pycparser", "distutils", "pydoc_data",
    "doctest", "unittest", "lib2to3", "tkinter",
]


def patch_spec(spec_path: str):
    """在 Analysis 之后插入裁剪逻辑：去掉用不到的 Qt 二进制 / 插件 / 翻译文件"""
    txt = open(spec_path, encoding="utf-8").read()
    if "_slim_toc" in txt:
        return
    inject = (
        "\n"
        "# ---- build_exe.py 注入：裁掉用不到的 Qt 二进制，减小体积 ----\n"
        "_DROP_EXACT = %r\n"
        "_DROP_SUFFIX = %r\n"
        "\n"
        "\n"
        "def _slim_toc(toc):\n"
        "    out = []\n"
        "    for e in toc:\n"
        "        n = (e[0] or '').replace('\\\\', '/')\n"
        "        low = n.lower()\n"
        "        if low.endswith('.qm'):            # Qt 自带翻译：未主动加载 QTranslator，用不到\n"
        "            continue\n"
        "        if any(low.endswith(d.lower()) for d in _DROP_EXACT):\n"
        "            continue\n"
        "        if any(d.lower() in low for d in _DROP_SUFFIX):\n"
        "            continue\n"
        "        out.append(e)\n"
        "    return out\n"
        "\n"
        "\n"
        "a.binaries = _slim_toc(a.binaries)\n"
        "a.datas = _slim_toc(a.datas)\n"
        "# ---- 注入结束 ----\n"
        "\n"
    ) % (tuple(QT_DROP_DLL), tuple(QT_DROP_PLUGIN))
    if "pyz = PYZ(" not in txt:
        print("  ! spec 结构异常，跳过裁剪")
        return
    txt = txt.replace("pyz = PYZ(", inject + "pyz = PYZ(", 1)
    open(spec_path, "w", encoding="utf-8").write(txt)
    print("  + spec 已注入 Qt 二进制裁剪（%d 条规则）"
          % (len(QT_DROP_DLL) + len(QT_DROP_PLUGIN)))


def app_version() -> str:
    src = open(SRC, encoding="utf-8").read()
    m = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', src, re.M)
    return m.group(1) if m else "0.0.0"


def has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def slim_build_dir():
    """把上次的 build/<NAME> 改名挪到 build/archive/（代替 --clean）。

    这里只改名、不删除：既避免 --clean / shutil.rmtree 覆盖旧缓存时的竞态，
    也保留历史构建缓存便于回溯。build/archive/ 攒多了可以手动整个删掉，不影响构建。
    """
    import time
    bdir = os.path.join(BASE, "build", NAME)
    if not os.path.isdir(bdir):
        return
    arc = os.path.join(BASE, "build", "archive")
    if not os.path.isdir(arc):
        os.makedirs(arc)
    dst = unique_path(os.path.join(arc, NAME + "_" + time.strftime("%m%d%H%M%S")))
    os.rename(bdir, dst)
    print("  已挪开上次构建缓存 -> build\\archive\\%s" % os.path.basename(dst))


def copy_uninstall_bat(dest_dir: str):
    """把卸载脚本放进程序目录（与 exe 同层），方便免安装用户直接卸载。"""
    bat = os.path.join(BASE, "卸载桌面歌词.bat")
    if os.path.isfile(bat) and os.path.isdir(dest_dir):
        shutil.copy2(bat, os.path.join(dest_dir, os.path.basename(bat)))
        print("  + 附带卸载脚本 卸载桌面歌词.bat")


def unique_path(path: str) -> str:
    """给已存在的路径拼一个不冲突的名字（只改名归档、不删除）"""
    import time
    if not os.path.exists(path):
        return path
    return "%s.%s" % (path, time.strftime("%m%d%H%M%S"))


def archive_old_dist(keep_ver: str):
    """把 dist 里的历史产物挪进 dist/archive/，只留当前版本。

    单文件 exe 一个就几十 MB，来回打包几次 dist 就上 GB 了；这里不删文件，
    只是移进归档子目录，需要旧版本还能找回来。
    """
    dist = os.path.join(BASE, "dist")
    if not os.path.isdir(dist):
        return
    arc = os.path.join(dist, "archive")
    moved = []
    for f in sorted(os.listdir(dist)):
        fp = os.path.join(dist, f)
        if not os.path.isfile(fp):
            continue
        low = f.lower()
        is_ver = low.startswith(NAME.lower() + "-v") and low.endswith(".exe")
        if is_ver and ("-v%s" % keep_ver).lower() in low:
            continue                       # 当前版本留着
        if is_ver or low.startswith(NAME.lower() + ".old"):
            if not os.path.isdir(arc):
                os.makedirs(arc)
            dst = unique_path(os.path.join(arc, f))
            os.rename(fp, dst)
            moved.append((f, os.path.getsize(dst) / 1048576.0))
    if moved:
        print("  + 已归档 %d 个历史产物 -> dist\\archive\\ (%.1f MB)"
              % (len(moved), sum(m for _, m in moved)))


def main() -> int:
    full_fonts = "--full" in sys.argv
    no_font = "--no-font" in sys.argv
    onedir = "--dir" in sys.argv
    ver = app_version()
    # 变体加后缀，免得「默认档」与「最小档」互相覆盖同名产物（都是 v2.4.15 会撞车）
    tag = "-lite" if no_font else ("-full" if full_fonts else "")
    print("== 桌面歌词打包 ==\n版本: %s" % ver)
    print("打包器: %s" % sys.executable)
    print("模式: %s / 字体: %s\n" % ("onedir" if onedir else "onefile",
                                  "不内置" if no_font else
                                  ("全字重" if full_fonts else "仅 Regular")))

    cmd = [sys.executable, "-m", "PyInstaller",
           "--noconfirm", "--clean",
           "--onedir" if onedir else "--onefile",
           "--noconsole",
           "--name", NAME,
           "--paths", BASE]

    # 防报毒基础三件套：真实图标 + 完整版本信息资源（详见 version_info.txt）。
    # 杀软启发式对「无图标、无版本信息」的 PyInstaller 产物最敏感。
    ico = os.path.join(BASE, "icon.ico")
    vinfo = os.path.join(BASE, "version_info.txt")
    if os.path.isfile(ico):
        cmd += ["--icon", ico]
    if os.path.isfile(vinfo):
        cmd += ["--version-file", vinfo]

    # 应用图标 PNG（托盘/窗口图标与 exe 图标同源；make_app_icon 运行时加载）
    icon_png = os.path.join(BASE, "icon.png")
    if os.path.isfile(icon_png):
        cmd += ["--add-data", icon_png + os.pathsep + "."]
        print("  + 内置应用图标 icon.png")

    # 内置字体目录（打包后作兜底，用户下载的字体在 %APPDATA% 下）
    fonts = os.path.join(BASE, "fonts")
    if no_font:
        # 体积最小档：不内置字体。默认字体会落到 Microsoft YaHei UI（系统自带），
        # 想要 MiSans 可以在设置面板的字体库里一键下载（下到 %APPDATA%，不占 exe）。
        print("  + 不内置字体：默认用系统 Microsoft YaHei UI；MiSans 可在设置面板一键下载")
    elif os.path.isdir(fonts):
        if full_fonts:
            cmd += ["--add-data", fonts + os.pathsep + "fonts"]
        else:
            keep = [f for f in sorted(os.listdir(fonts))
                    if f.lower().endswith((".ttf", ".otf", ".ttc")) and "Regular" in f]
            # 用系统临时目录：每次都是干净的新目录，免去 rmtree
            import tempfile
            tmp = tempfile.mkdtemp(prefix="dl_fonts_")
            for f in keep:
                shutil.copy2(os.path.join(fonts, f), os.path.join(tmp, f))
            src_dir = tmp if keep else fonts
            cmd += ["--add-data", src_dir + os.pathsep + "fonts"]
            print("  + 内置字体(%s): %s" % ("精简" if keep else "回退全量",
                                       ", ".join(keep) if keep else "全目录"))

    # 本项目完全不用 pywin32；本机 pywin32 装残了（缺 pywintypes38.dll），
    # PyInstaller 的 pythoncom hook 会因此直接崩，故整族排除。
    for mod in ("win32com", "pythoncom", "pywintypes", "win32api", "win32con",
                "win32gui", "win32event", "win32file", "win32process",
                "win32security", "win32service", "adodbapi", "isapi"):
        cmd += ["--exclude-module", mod]

    for mod in QT_EXCLUDE + PKG_EXCLUDE:
        cmd += ["--exclude-module", mod]

    # SMTC 媒体监听后端：Python<3.12 用 winsdk，>=3.12 用 winrt
    if has("winsdk"):
        for sub in WINSDK_NEEDED:
            cmd += ["--collect-submodules", sub]
    elif has("winrt"):
        cmd += ["--collect-submodules", "winrt.windows.media.control",
                "--collect-submodules", "winrt.windows.storage.streams"]
        print("  + 精准收集 winrt")

    if has("Crypto"):
        cmd += ["--hidden-import", "Crypto"]   # pycryptodome，网易云歌词接口用
        print("  + 收集 Crypto")

    cmd.append(SRC)

    # PyInstaller 覆盖旧产物时会对 dist/Desktop-sing.exe（onefile）做 os.remove、
    # 对 dist/Desktop-sing/（onedir 的 COLLECT）做 shutil.rmtree。若旧产物正被占用
    # 或删除被拦截，构建会直接失败（报 "Some operations were aborted"）。
    # 统一先把旧产物改名挪开，绕开删除。（onedir 只在第二次打包时才会踩到，容易漏。）
    if onedir:
        ddir = os.path.join(BASE, "dist", NAME)
        if os.path.isdir(ddir):
            arc = os.path.join(BASE, "dist", "archive")
            if not os.path.isdir(arc):
                os.makedirs(arc)
            trash = unique_path(os.path.join(arc, NAME + ".prev"))
            os.rename(ddir, trash)
            print("  已挪开旧目录产物 -> %s" % trash)
    else:
        old = os.path.join(BASE, "dist", NAME + ".exe")
        if os.path.isfile(old):
            arc = os.path.join(BASE, "dist", "archive")
            if not os.path.isdir(arc):
                os.makedirs(arc)
            trash = unique_path(os.path.join(arc, NAME + ".prev.exe"))
            os.rename(old, trash)
            print("  已挪开旧产物 -> %s" % trash)

    # ---------------------------------------------------------------
    # --exclude-module 只能去掉 PySide6 的 .pyd 绑定，Qt 的 DLL 是 hook
    # 按目录整包收进来的（opengl32sw 19.7MB、QtQml/Quick/Pdf 等）。所以先
    # 生成 spec，再在 Analysis 之后把用不到的二进制/插件筛掉，最后按 spec 构建。
    # ---------------------------------------------------------------
    spec_path = os.path.join(BASE, NAME + ".spec")
    # 注意：PyInstaller 的 console-script 包装器（pyi-makespec.exe）在部分环境下会
    # **静默失败** —— 退出码 1、没有任何输出。一旦中招，整条「生成 spec → 注入 Qt
    # 裁剪 → 按 spec 构建」的链路会被跳过，退回不带裁剪的直接打包，产出的 exe 会
    # 大出十几 MB（Qml/Quick/Pdf/opengl32sw 全都在）。所以优先用模块方式调用。
    spec_args = [a for a in cmd[3:] if a not in ("--noconfirm", "--clean", "-y")]
    makers = (
        [sys.executable, "-m", "PyInstaller.utils.cliutils.makespec"],
        [os.path.join(os.path.dirname(sys.executable), "pyi-makespec.exe")],
    )
    made = False
    for tool in makers:
        r = subprocess.run(tool + ["--specpath", BASE] + spec_args, cwd=BASE)
        if r.returncode == 0 and os.path.isfile(spec_path):
            made = True
            break
        print("  ! %s 生成 spec 失败（exit=%d），换下一种调用方式"
              % (tool[-1] if isinstance(tool[-1], str) else tool[1], r.returncode))
    if made:
        patch_spec(spec_path)
        # 不用 --clean（会删除整棵 build 目录），改用「改名挪开 build 目录」达到同样效果
        slim_build_dir()
        r = subprocess.run([sys.executable, "-m", "PyInstaller",
                            "--noconfirm", spec_path], cwd=BASE)
    else:
        print("\n[失败] 生成 spec 失败，退回直接打包（不裁剪 Qt DLL，产物会大十几 MB！）")
        r = subprocess.run(cmd, cwd=BASE)
    if r.returncode != 0:
        print("\n[失败] PyInstaller 返回 %d" % r.returncode)
        return r.returncode

    # onedir 的产物在 dist/<NAME>/<NAME>.exe，不是 dist/<NAME>.exe（这里以前只认 onefile 的路径，
    # 导致 --dir 明明构建成功却被判为「未找到产物」）
    exe = (os.path.join(BASE, "dist", NAME, NAME + ".exe") if onedir
           else os.path.join(BASE, "dist", NAME + ".exe"))
    if not os.path.isfile(exe):
        print("\n[失败] 未找到产物 %s" % exe)
        return 1

    if onedir:
        out = os.path.join(BASE, "dist", "%s-v%s%s" % (NAME, ver, tag))
        if os.path.isdir(out):
            # 同名目标已存在：只改名挪进 archive，不直接删除
            arc = os.path.join(BASE, "dist", "archive")
            if not os.path.isdir(arc):
                os.makedirs(arc)
            os.rename(out, unique_path(os.path.join(arc, os.path.basename(out) + ".prev")))
        os.rename(os.path.join(BASE, "dist", NAME), out)
        copy_uninstall_bat(out)
        total = sum(os.path.getsize(os.path.join(dp, f))
                    for dp, _, fs in os.walk(out) for f in fs)
        print("\n[完成] %s\\  (%.1f MB)" % (out, total / 1048576.0))
        return 0

    out = os.path.join(BASE, "dist", "%s-v%s%s.exe" % (NAME, ver, tag))
    shutil.copy2(exe, out)
    copy_uninstall_bat(os.path.dirname(out))   # 单文件版：把卸载脚本放同目录
    archive_old_dist(ver)
    print("\n[完成] %s  (%.1f MB)" % (out, os.path.getsize(out) / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
