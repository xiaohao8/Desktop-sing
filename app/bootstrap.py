# -*- coding: utf-8 -*-
"""GUI startup orchestration."""
from __future__ import annotations

import ctypes
import os
import platform
import sys
import traceback
import urllib.request

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .context import AppContext
from .runtime import ApplicationRuntime

_instance_guard = None


def _network_preflight(runtime):
    idna_ok = runtime.ensure_idna_codec()
    proxy_hint = ""
    if runtime._system_proxy_set():
        try:
            proxies = urllib.request.getproxies()
            proxy_hint = "，检测到系统代理 %s" % (
                proxies.get("https") or proxies.get("http") or "")
        except Exception:
            proxy_hint = "，检测到系统代理"
    runtime.log("联网准备：idna=%s，出口=直连优先%s"
                % ("可用" if idna_ok else "缺失", proxy_hint))


def _settle_memory():
    try:
        import gc

        gc.collect()
        gc.freeze()
    except Exception:
        pass
    try:
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.SetProcessWorkingSetSize(handle, -1, -1)
    except Exception:
        pass


def build_runtime(argv=None, watcher_factory=None) -> ApplicationRuntime:
    import lyrics_overlay as runtime

    context = AppContext.from_runtime(runtime, list(argv if argv is not None else sys.argv))
    return ApplicationRuntime(context, watcher_factory=watcher_factory)


def run(argv=None) -> int:
    global _instance_guard
    import lyrics_overlay as runtime

    args = list(argv if argv is not None else sys.argv)
    app = QApplication(args)
    app.setApplicationName("桌面歌词")
    app.setApplicationVersion(runtime.APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(runtime.make_app_icon())

    probe = runtime._instance_alive()
    if probe:
        runtime._close_handle(probe)
        if runtime._request_takeover():
            runtime.log("旧实例已让位，v%s 接管启动" % runtime.APP_VERSION)
        else:
            runtime.log("已有实例在运行且未响应接管请求，本次启动退出")
            try:
                runtime.styled_message(
                    None,
                    "桌面歌词",
                    "旧版本桌面歌词仍在运行且无法自动接管。",
                    "请右键托盘图标选择「退出」后再重新启动。",
                    warning=True,
                )
            except Exception:
                pass
            return 0

    _instance_guard = runtime._acquire_instance_mutex()
    runtime._instance_guard = _instance_guard

    runtime._load_fonts()
    _network_preflight(runtime)
    runtime.log("桌面歌词 v%s 启动（python %s）"
                % (runtime.APP_VERSION, platform.python_version()))

    application = build_runtime(args)
    application.start()
    QTimer.singleShot(3000, _settle_memory)
    return int(app.exec())


def write_fatal() -> None:
    import lyrics_overlay as runtime

    try:
        with open(os.path.join(runtime.CFG_DIR, "fatal.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write(traceback.format_exc())
    except OSError:
        pass
    runtime.log("fatal:\n" + traceback.format_exc())
