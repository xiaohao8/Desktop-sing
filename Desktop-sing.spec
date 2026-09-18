# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['Crypto']
hiddenimports += collect_submodules('winsdk.windows.media.control')
hiddenimports += collect_submodules('winsdk.windows.storage.streams')
hiddenimports += collect_submodules('winsdk.windows.foundation')
hiddenimports += collect_submodules('winsdk.windows.foundation.collections')
hiddenimports += collect_submodules('winsdk.windows.storage')


a = Analysis(
    ['C:/Users/35436/Desktop/代码/desktop-lyrics/lyrics_overlay.py'],
    pathex=['C:/Users/35436/Desktop/代码/desktop-lyrics'],
    binaries=[],
    datas=[('C:/Users/35436/Desktop/代码/desktop-lyrics/icon.png', '.'), ('C:/Users/35436/AppData/Local/Temp/dl_fonts_sjmrxniz', 'fonts')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['win32com', 'pythoncom', 'pywintypes', 'win32api', 'win32con', 'win32gui', 'win32event', 'win32file', 'win32process', 'win32security', 'win32service', 'adodbapi', 'isapi', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtVirtualKeyboard', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtTest', 'PySide6.QtUiTools', 'PySide6.QtPrintSupport', 'PySide6.QtSql', 'PySide6.QtConcurrent', 'PySide6.QtScxml', 'PySide6.QtStateMachine', 'PySide6.QtSpatialAudio', 'PySide6.QtTextToSpeech', 'setuptools', 'pkg_resources', 'pycparser', 'distutils', 'pydoc_data', 'doctest', 'unittest', 'lib2to3', 'tkinter'],
    noarchive=False,
    optimize=0,
)

# ---- build_exe.py 注入：裁掉用不到的 Qt 二进制，减小体积 ----
_DROP_EXACT = ('opengl32sw.dll', 'Qt6Quick.dll', 'Qt6QuickControls2.dll', 'Qt6QuickWidgets.dll', 'Qt6Quick3D.dll', 'Qt6Quick3DCore.dll', 'Qt6Quick3DRender.dll', 'Qt6Quick3DUtils.dll', 'Qt6Quick3DAssetImport.dll', 'Qt6QuickShapes.dll', 'Qt6QuickParticles.dll', 'Qt6QuickEffects.dll', 'Qt6QuickLayouts.dll', 'Qt6Qml.dll', 'Qt6QmlModels.dll', 'Qt6QmlCore.dll', 'Qt6QmlWorkerScript.dll', 'Qt6QmlNetwork.dll', 'Qt6QmlXmlListModel.dll', 'Qt6QmlLocalStorage.dll', 'Qt6QmlCompiler.dll', 'Qt6QmlMeta.dll', 'Qt6Pdf.dll', 'Qt6PdfWidgets.dll', 'Qt6PdfQuick.dll', 'Qt6OpenGL.dll', 'Qt6OpenGLWidgets.dll', 'Qt6Svg.dll', 'Qt6SvgWidgets.dll', 'Qt6VirtualKeyboard.dll', 'Qt6Charts.dll', 'Qt6ChartsQml.dll', 'Qt6DataVisualization.dll', 'Qt6DataVisualizationQml.dll', 'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll', 'Qt6MultimediaQuick.dll', 'Qt6WebEngineCore.dll', 'Qt6WebEngineWidgets.dll', 'Qt6WebEngineQuick.dll', 'Qt6WebSockets.dll', 'Qt6WebChannel.dll', 'Qt63DCore.dll', 'Qt63DRender.dll', 'Qt63DInput.dll', 'Qt63DLogic.dll', 'Qt63DAnimation.dll', 'Qt63DExtras.dll', 'Qt63DQuick.dll', 'Qt6Sql.dll', 'Qt6Test.dll', 'Qt6Designer.dll', 'Qt6Help.dll', 'Qt6PrintSupport.dll', 'Qt6Concurrent.dll', 'Qt6Scxml.dll', 'Qt6StateMachine.dll', 'Qt6SpatialAudio.dll', 'Qt6TextToSpeech.dll', 'Qt6SerialPort.dll', 'Qt6ShaderTools.dll', 'Qt6DBus.dll', 'Qt6Nfc.dll', 'Qt6Positioning.dll', 'Qt6PositioningQuick.dll', 'Qt6RemoteObjects.dll', 'Qt6Sensors.dll', 'Qt6Bluetooth.dll', 'Qt6Bodymovin.dll', 'Qt6 Labs*.dll', 'libcrypto-3-x64.dll', 'libssl-3-x64.dll')
_DROP_SUFFIX = ('platforms/qdirect2d.dll', 'platforms/qminimal.dll', 'platforms/qoffscreen.dll', 'imageformats/qtiff.dll', 'imageformats/qicns.dll', 'imageformats/qico.dll', 'imageformats/qtga.dll', 'imageformats/qwbmp.dll', 'imageformats/qpdf.dll', 'imageformats/qsvg.dll', 'iconengines/qsvgicon.dll', 'virtualkeyboard/qtvirtualkeyboardplugin.dll', 'tls/qopensslbackend.dll')


def _slim_toc(toc):
    out = []
    for e in toc:
        n = (e[0] or '').replace('\\', '/')
        low = n.lower()
        if low.endswith('.qm'):            # Qt 自带翻译：未主动加载 QTranslator，用不到
            continue
        if any(low.endswith(d.lower()) for d in _DROP_EXACT):
            continue
        if any(d.lower() in low for d in _DROP_SUFFIX):
            continue
        out.append(e)
    return out


a.binaries = _slim_toc(a.binaries)
a.datas = _slim_toc(a.datas)
# ---- 注入结束 ----

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Desktop-sing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:/Users/35436/Desktop/代码/desktop-lyrics/version_info.txt',
    icon=['C:/Users/35436/Desktop/代码/desktop-lyrics/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Desktop-sing',
)
