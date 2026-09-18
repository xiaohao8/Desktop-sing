# -*- coding: utf-8 -*-
"""
桌面歌词（Desktop-sing）

读取 Windows 系统媒体控制（SMTC）中正在播放的歌曲（QQ音乐 / 网易云 / Spotify / 浏览器
均可，只要播放器接入了系统媒体栏），自动获取专辑封面与歌词，以悬浮条形式显示在桌面：
逐字滑动卡拉OK动画、封面主色取色、翻译歌词、氛围光晕、5 种悬浮样式、全局快捷键，
常驻桌面/置顶悬浮双模式。

用法:
    pythonw lyrics_overlay.py       # 无控制台启动
依赖:
    pip install PySide6 winsdk pycryptodome      # Python <= 3.11
    pip install PySide6 winrt-Windows.Media.Control winrt-Windows.Storage.Streams pycryptodome
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import ctypes
import hashlib
import json
import math
import os
import platform
import random
import re
import string
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import zlib

from PySide6.QtCore import (
    QObject, QPropertyAnimation, Qt, QTimer, QPointF, QPoint,
    QRectF, QEasingCurve, QVariantAnimation, Signal, QSize, QUrl,
)
from PySide6.QtGui import (
    QAction, QBrush, QColor, QCursor, QDesktopServices, QFont, QFontDatabase,
    QFontMetrics, QIcon, QImage, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# ---- SMTC 绑定：延迟导入 ----------------------------------------------------
# 只 import winsdk 就要 ~155ms（它是一大坨 winrt 投影模块），启动关键路径上完全没必要
# 先付这笔钱。真正的导入挪到采集线程第一次跑的时候，那时主线程正在建窗/画首帧，
# 用户看到窗口的时间提前，采集数据晚一两百毫秒到达并无感。
MediaManager = None
DataReader = None


def _load_smtc() -> bool:
    """按需导入 SMTC 绑定，成功返回 True（重复调用只付一次导入）"""
    global MediaManager, DataReader
    if MediaManager is not None:
        return True
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as _Mgr,
        )
        from winsdk.windows.storage.streams import DataReader as _Reader
    except ImportError:  # Python >= 3.12 的 winrt-* 命名空间包
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as _Mgr,
            )
            from winrt.windows.storage.streams import DataReader as _Reader
        except ImportError:
            log("SMTC 绑定不可用：需要 winsdk（或 winrt-Windows.Media.Control）")
            return False
    MediaManager, DataReader = _Mgr, _Reader
    return True

APP_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "Desktop-sing"
CFG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CACHE_DIR = os.path.join(CFG_DIR, "cache")
CONFIG_PATH = os.path.join(CFG_DIR, "config.json")
os.makedirs(CACHE_DIR, exist_ok=True)

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_log_lock = threading.Lock()

# pycryptodome 只服务网易云 weapi 加密接口；import 它要 ~80ms。这里同样延迟：
# _HAS_CRYPTO=None 表示「还没探过」，第一次真要用网易云接口时才 import。
_HAS_CRYPTO = None


def _crypto_ready() -> bool:
    """pycryptodome 是否可用：先用 find_spec 廉价探测（不执行包体），真用上才 import AES"""
    global _HAS_CRYPTO
    if _HAS_CRYPTO is None:
        try:
            import importlib.util as _ilu
            _HAS_CRYPTO = _ilu.find_spec("Crypto") is not None
        except Exception:
            _HAS_CRYPTO = False
    return _HAS_CRYPTO

# 字体（main 里加载 fonts/ 下的 MiSans，失败时回落）
FONT_CUR = "Microsoft YaHei UI"   # 当前句
FONT_REG = "Microsoft YaHei UI"   # 下一句/次要
FONT_MED = "Microsoft YaHei UI"   # 标题行
CUR_BOLD = True

# 字体目录：程序自带的 fonts/（只读）+ 用户下载的 %APPDATA%/Desktop-sing/fonts（可写）
# 打包成 exe 后程序目录可能不可写，下载字体一律放用户目录
BUNDLED_FONT_DIR = os.path.join(APP_DIR, "fonts")
USER_FONT_DIR = os.path.join(CFG_DIR, "fonts")

LOADED_FAMILIES = []      # 由字体文件加载出来的族名（自带 + 已下载）
FONT_LIBRARY_CACHE = None  # 已装字体族 -> 字体库条目 id

# 免费商用字体库：一键下载，不局限于系统已装字体
#   主 URL：走 jsDelivr / GitHub Release（境外 CDN，访问慢或超时就切换国内镜像）
#   国内镜像：npmmirror(阿里) / ghproxy / 知乎 ghproxy / 思源仓库镜像
#   每个条目 files: [(保存文件名, [主地址, 镜像1, 镜像2...]), ...]；zip: 解压挑字体
FONT_LIBRARY = [
    {"id": "dingtalk", "name": "钉钉进步体", "mb": 2.1,
     "note": "7° 倾斜的标题体，年轻有活力，钉钉官方免费商用",
     "files": [("DingTalkJinBuTi-Regular.ttf",
                ["https://cdn.jsdelivr.net/gh/muzihuaner/txfont@main/DingTalk%20JinBuTi.ttf",
                 "https://ghfast.top/https://github.com/muzihuaner/txfont/raw/main/DingTalk%20JinBuTi.ttf",
                 "https://ghproxy.net/https://github.com/muzihuaner/txfont/raw/main/DingTalk%20JinBuTi.ttf",
                 "https://cdn.jsdelivr.net/gh/muzihuaner/txfont@main/DingTalk%20JinBuTi.ttf"])]},
    {"id": "misans", "name": "MiSans", "mb": 7.9,
     "note": "小米出品，中性清晰，默认字体，免费商用",
     "files": [("MiSans-Static.ttf",
                ["https://cdn.jsdelivr.net/gh/adivenxnataly/MiSans@main/MiSans/MiSans-Static.ttf",
                 "https://ghfast.top/https://github.com/adivenxnataly/MiSans/raw/main/MiSans/MiSans-Static.ttf",
                 "https://ghproxy.net/https://github.com/adivenxnataly/MiSans/raw/main/MiSans/MiSans-Static.ttf"])]},
    {"id": "alibaba", "name": "阿里巴巴普惠体 3.0", "mb": 17.0,
     "note": "阿里官方免费商用，中英文兼顾，字重齐全",
     "files": [("AlibabaPuHuiTi-3-55-Regular.ttf",
                ["https://cdn.jsdelivr.net/gh/hongzhi725/AlibabaPuHuiTi@master/font/"
                 "AlibabaPuHuiTi/AlibabaPuHuiTi-3-55-Regular/AlibabaPuHuiTi-3-55-Regular.ttf",
                 "https://ghfast.top/https://github.com/hongzhi725/AlibabaPuHuiTi/raw/master/font/"
                 "AlibabaPuHuiTi/AlibabaPuHuiTi-3-55-Regular/AlibabaPuHuiTi-3-55-Regular.ttf",
                 "https://ghproxy.net/https://github.com/hongzhi725/AlibabaPuHuiTi/raw/master/font/"
                 "AlibabaPuHuiTi/AlibabaPuHuiTi-3-55-Regular/AlibabaPuHuiTi-3-55-Regular.ttf"]),
               ("AlibabaPuHuiTi-3-65-Medium.ttf",
                ["https://cdn.jsdelivr.net/gh/hongzhi725/AlibabaPuHuiTi@master/font/"
                 "AlibabaPuHuiTi/AlibabaPuHuiTi-3-65-Medium/AlibabaPuHuiTi-3-65-Medium.ttf",
                 "https://ghfast.top/https://github.com/hongzhi725/AlibabaPuHuiTi/raw/master/font/"
                 "AlibabaPuHuiTi/AlibabaPuHuiTi-3-65-Medium/AlibabaPuHuiTi-3-65-Medium.ttf",
                 "https://ghproxy.net/https://github.com/hongzhi725/AlibabaPuHuiTi/raw/master/font/"
                 "AlibabaPuHuiTi/AlibabaPuHuiTi-3-65-Medium/AlibabaPuHuiTi-3-65-Medium.ttf"])]},
    {"id": "noto", "name": "思源黑体 / Noto Sans SC", "mb": 17.8,
     "note": "开源 SIL OFL，字形规整，屏幕阅读性极佳",
     "files": [("NotoSansSC-VF.ttf",
                ["https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/notosanssc/"
                 "NotoSansSC%5Bwght%5D.ttf",
                 "https://ghfast.top/https://raw.githubusercontent.com/google/fonts/main/ofl/"
                 "notosanssc/NotoSansSC%5Bwght%5D.ttf",
                 "https://ghproxy.net/https://raw.githubusercontent.com/google/fonts/main/ofl/"
                 "notosanssc/NotoSansSC%5Bwght%5D.ttf"])]},
    {"id": "wenkai", "name": "霞鹜文楷", "mb": 25.6,
     "note": "开源 SIL OFL，手写楷体气质，适合抒情慢歌",
     "files": [("LXGWWenKai-Regular.ttf",
                ["https://github.com/lxgw/LxgwWenKai/releases/download/v1.522/"
                 "LXGWWenKai-Regular.ttf",
                 "https://ghfast.top/https://github.com/lxgw/LxgwWenKai/releases/download/"
                 "v1.522/LXGWWenKai-Regular.ttf",
                 "https://ghproxy.net/https://github.com/lxgw/LxgwWenKai/releases/download/"
                 "v1.522/LXGWWenKai-Regular.ttf",
                 "https://mirror.ghproxy.com/https://github.com/lxgw/LxgwWenKai/releases/"
                 "download/v1.522/LXGWWenKai-Regular.ttf"])]},
    {"id": "smiley", "name": "得意黑", "mb": 5.8,
     "note": "开源 SIL OFL，强对比斜体美术字，很抓眼",
     "files": [("smiley-sans.zip",
                ["https://github.com/atelier-anchor/smiley-sans/releases/download/"
                 "v2.0.1/smiley-sans-v2.0.1.zip",
                 "https://ghfast.top/https://github.com/atelier-anchor/smiley-sans/releases/"
                 "download/v2.0.1/smiley-sans-v2.0.1.zip",
                 "https://ghproxy.net/https://github.com/atelier-anchor/smiley-sans/releases/"
                 "download/v2.0.1/smiley-sans-v2.0.1.zip"])], "zip": True},
]


# 已加载族名 → 字体库条目的匹配关键词（字体厂商命名差异大，用关键词兜住）
FONT_MATCH = {
    "dingtalk": ("dingtalk", "钉钉"),
    "misans": ("misans", "mi sans"),
    "alibaba": ("alibaba", "puhuiti", "普惠"),
    "noto": ("noto", "source han", "思源"),
    "wenkai": ("lxgw", "wenkai", "文楷"),
    "smiley": ("smiley", "得意"),
}


def _font_family_match(family: str, entry_id: str) -> bool:
    f = (family or "").lower()
    return any(k in f for k in FONT_MATCH.get(entry_id, ()))


def _pick_family(families) -> str:
    """从一组族名里挑最合适的字重：Semibold > Bold > Medium > 其它"""
    fams = [f for f in (families or []) if f]
    for pref in ("semibold", "bold", "medium", "regular"):
        for f in fams:
            if pref in f.lower():
                return f
    return fams[0] if fams else ""


def _scan_font_files():
    out = []
    for d in (BUNDLED_FONT_DIR, USER_FONT_DIR):
        if not os.path.isdir(d):
            continue
        for root, _dirs, names in os.walk(d):
            for n in names:
                if n.lower().endswith((".ttf", ".otf", ".ttc")):
                    out.append(os.path.join(root, n))
    return sorted(set(out))


def load_font_file(path: str) -> list:
    """加载单个字体文件，返回其中的族名列表"""
    try:
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            return []
        return list(QFontDatabase.applicationFontFamilies(fid))
    except Exception:
        log("字体加载失败 %s:\n%s" % (path, traceback.format_exc()))
        return []


def _load_fonts():
    """扫描字体目录（自带 + 已下载）全部加载；MiSans 作为默认首选"""
    global FONT_CUR, FONT_REG, FONT_MED, CUR_BOLD, LOADED_FAMILIES
    loaded = []
    for p in _scan_font_files():
        loaded += load_font_file(p)
    # 去重保序
    seen, fams = set(), []
    for f in loaded:
        if f and f not in seen:
            seen.add(f)
            fams.append(f)
    LOADED_FAMILIES = fams
    if "MiSans Semibold" in fams:
        FONT_CUR, CUR_BOLD = "MiSans Semibold", False
    elif "MiSans" in fams:
        FONT_CUR, CUR_BOLD = "MiSans", False
    if "MiSans Medium" in fams:
        FONT_MED = "MiSans Medium"
    elif "MiSans" in fams:
        FONT_MED = "MiSans"
    if "MiSans" in fams:
        FONT_REG = "MiSans"
    return fams


def font_library_state() -> dict:
    """返回 {字体库 id: (是否已下载, 已加载的族名列表)}"""
    installed = set(LOADED_FAMILIES) | set(QFontDatabase.families())
    state = {}
    for ent in FONT_LIBRARY:
        files = [os.path.join(USER_FONT_DIR, f[0]) for f in ent["files"]]
        files += [os.path.join(BUNDLED_FONT_DIR, f[0]) for f in ent["files"]]
        have = any(os.path.exists(p) and os.path.getsize(p) > 1024 for p in files)
        state[ent["id"]] = bool(have)
    return state


def download_font(entry: dict, on_progress=None) -> list:
    """下载并安装字体库条目，返回加载到的族名。on_progress(done, total, name)

    每个文件按「主 CDN → 国内镜像」顺序逐个尝试，主站/镜像整体失败才换下一个镜像；
    已在本地且大小正常的文件直接跳过，不会重复下载。
    """
    import zipfile
    os.makedirs(USER_FONT_DIR, exist_ok=True)
    families = []
    for fname, urls in entry["files"]:
        if isinstance(urls, str):        # 兼容老格式（单地址）
            urls = [urls]
        dst = os.path.join(USER_FONT_DIR, fname)
        if not (os.path.exists(dst) and os.path.getsize(dst) > 1024):
            tmp = dst + ".part"
            fetched = False
            exc_hint = ""
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        total = int(r.headers.get("Content-Length") or 0)
                        done = 0
                        with open(tmp, "wb") as f:
                            while True:
                                chunk = r.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                                done += len(chunk)
                                if on_progress:
                                    on_progress(done, total, entry["name"])
                    os.replace(tmp, dst)
                    fetched = True
                    break
                except Exception as ex:
                    exc_hint = "%s: %s" % (url, ex)
                    log("字体镜像失败 %s (%s)" % (fname, url))
                    continue
            if not fetched:
                raise RuntimeError("字体下载失败：%s" % exc_hint)
        if fname.lower().endswith(".zip"):    # 压缩包：挑出字体文件解压
            try:
                with zipfile.ZipFile(dst) as z:
                    for zf in z.namelist():
                        if zf.lower().endswith((".ttf", ".otf")):
                            out = os.path.join(USER_FONT_DIR, os.path.basename(zf))
                            if not os.path.exists(out):
                                with z.open(zf) as src, open(out, "wb") as fp:
                                    fp.write(src.read())
                            families += load_font_file(out)
            except Exception:
                log("字体解压失败:\n" + traceback.format_exc())
        else:
            families += load_font_file(dst)
    return families


def log(msg: str):
    with _log_lock:
        try:
            with open(os.path.join(CFG_DIR, "desktop-lyrics.log"), "a", encoding="utf-8") as f:
                f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
        except OSError:
            pass


# 播放控制：注入系统媒体键（等价于按下键盘的 播放/暂停、上一首、下一首键，
# QQ音乐 / 网易云 / Spotify / 浏览器 等接入系统媒体栏的播放器都会响应）
_MEDIA_KEY = {"toggle": 0xB3, "next": 0xB0, "prev": 0xB1}


def send_media_command(cmd: str):
    vk = _MEDIA_KEY.get(cmd)
    if not vk:
        return
    try:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
    except Exception:
        log("media key failed: " + cmd)


# ======================================================================
# 全局快捷键：RegisterHotKey + 独立消息循环线程
#   优点：无需窗口焦点、不依赖 Qt 原生事件过滤器（跨 PySide6 版本更稳）
#   同一组热键被别的程序占用时自动跳过，不影响其它功能
# ======================================================================

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008
MOD_NOREPEAT = 0x4000

# (动作, 说明, 组合键显示, 修饰键, 虚拟键码)
HOTKEY_DEFS = [
    # 注意：Ctrl+Alt+方向键常被 Intel 显卡驱动「屏幕旋转」占用，这里改用 , / . 更稳
    ("toggle", "播放 / 暂停",    "Ctrl+Alt+P", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x50),
    ("prev",   "上一首",         "Ctrl+Alt+,", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0xBC),
    ("next",   "下一首",         "Ctrl+Alt+.", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0xBE),
    ("early",  "歌词提前 0.5 秒", "Ctrl+Alt+[", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0xDB),
    ("late",   "歌词延后 0.5 秒", "Ctrl+Alt+]", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0xDD),
    ("show",   "显示 / 隐藏",    "Ctrl+Alt+L", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x4C),
    ("panel",  "打开设置面板",    "Ctrl+Alt+S", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x53),
    ("style",  "切换悬浮样式",    "Ctrl+Alt+T", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x54),
    ("mode",   "切换显示模式",    "Ctrl+Alt+D", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x44),
    ("lock",   "锁定 / 解锁位置", "Ctrl+Alt+G", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x47),
    ("saver",  "氛围屏保",        "Ctrl+Alt+B", MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x42),
]


class GlobalHotkeys(QObject):
    """全局热键管理器：后台线程注册并监听 WM_HOTKEY，命中后发信号（跨线程自动排队到主线程）"""

    triggered = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = {}          # hotkey id -> 动作（供外部查看已生效的组合）
        self._failed = []       # 被其它程序占用的组合
        self._tid = 0
        self._running = False
        self._thread = None

    def register(self) -> bool:
        """启动热键线程并注册；重复调用安全"""
        if self._running:
            return True
        try:
            ctypes.windll.user32
        except Exception:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _loop(self):
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        self._tid = k32.GetCurrentThreadId()
        ids, failed = {}, []
        for idx, (act, _desc, combo, mods, vk) in enumerate(HOTKEY_DEFS):
            hid = 0xB000 + idx
            try:
                if u32.RegisterHotKey(None, hid, mods, vk):
                    ids[hid] = act
                else:
                    failed.append(combo)
            except Exception:
                failed.append(combo)
        self._ids, self._failed = ids, failed
        if failed:
            log("hotkey 被占用，已跳过: " + ", ".join(failed))
        msg = ctypes.wintypes.MSG()
        while True:
            try:
                r = u32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            except Exception:
                break
            if r in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                act = ids.get(int(msg.wParam))
                if act:
                    self.triggered.emit(act)
        for hid in list(ids):
            try:
                u32.UnregisterHotKey(None, hid)
            except Exception:
                pass

    def unregister(self):
        """同步注销：等热键线程退出，避免随后立刻 re-register 时相互抢占"""
        self._running = False
        if self._tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.5)
        self._tid = 0
        self._thread = None
        self._ids = {}
        self._failed = []


# ======================================================================
# 歌词获取：QQ音乐 / 网易云（含逐字 YRC）-> LRCLIB 兜底
# ======================================================================

def http_get(url: str, headers=None, timeout: float = 6.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ======================================================================
# 检查更新：版本比较 + 更新清单解析（GitHub Releases / 通用 JSON 清单）
# ======================================================================

def parse_version(v: str):
    """把 'v1.2.3' / '1.2' / '1.2.3.4' 规整成可比较的整数元组 (主,次,修订)"""
    v = (v or "").strip().lstrip("vV")
    parts = []
    for p in re.split(r"[.\-_]", v):
        m = re.match(r"\d+", p)
        parts.append(int(m.group()) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def compare_version(a: str, b: str) -> int:
    """a<b → -1；a==b → 0；a>b → 1"""
    pa, pb = parse_version(a), parse_version(b)
    return (pa > pb) - (pa < pb)


def resolve_update_url(url: str) -> str:
    """把 GitHub 网页版 releases/latest 链接改写成 API 链接（GitHub API 返回 JSON）。

    用户填 github.com/<owner>/<repo>/releases/latest 也能自动识别，
    不必强求手敲 api.github.com 的链路。
    """
    url = (url or "").strip()
    if "github.com" in url and "/releases/latest" in url and "api.github.com" not in url:
        m = re.search(r"github\.com/([^/]+)/([^/]+)/releases/latest", url)
        if m:
            return "https://api.github.com/repos/%s/%s/releases/latest" % (m.group(1), m.group(2))
    return url


def parse_update_payload(data: bytes, url: str) -> dict:
    """解析更新清单，返回 {'version':str,'url':str,'notes':str,'name':str} 或 None。

    支持两种来源：
      1) GitHub Releases API（api.github.com/repos/.../releases/latest）：
         取 tag_name 作版本，取第一个 .exe/.zip/.7z 资源的 browser_download_url 作下载地址；
      2) 通用 JSON 清单：{"version":..., "url":..., "notes":..., "name":...}
         其中 url 可以是任意直链，**含蓝奏云分享链接**（把蓝奏云的下载页 URL 填进字段即可）。
    """
    try:
        obj = json.loads(data.decode("utf-8", "ignore"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    # GitHub Releases
    if "tag_name" in obj:
        ver = str(obj.get("tag_name", "")).lstrip("vV") or ""
        notes = str(obj.get("body", "") or "").strip()
        dl = ""
        assets = obj.get("assets") or []
        if isinstance(assets, list):
            cands = [a for a in assets if isinstance(a, dict)
                     and (a.get("name") or "").lower().endswith((".exe", ".zip", ".7z"))]
            # 优先安装版 exe（升级场景最常用），其次才是压缩包；
            # 不能只取「第一个匹配项」—— assets 顺序由 GitHub 决定，zip 可能排在 exe 前面。
            for ext in (".exe", ".zip", ".7z"):
                for a in cands:
                    if (a.get("name") or "").lower().endswith(ext):
                        # GitHub 用 browser_download_url，Gitee 同名字段/ download_url 都见过，
                        # 逐个兜；但不用裸 "url"（那是 API 地址，不是下载直链）
                        dl = (a.get("browser_download_url") or ""
                              or a.get("download_url") or "")
                        if dl:
                            break
                if dl:
                    break
        if not dl:
            # 资源没给出下载直链时回落到对应平台的 Releases 页（Gitee 的 API 返回体略不同于 GitHub）
            dl = (obj.get("html_url") or ""
                  or (GITEE_RELEASES_PAGE if "gitee.com" in str(url) else GITHUB_RELEASES_PAGE))
        return {"version": ver, "url": dl, "notes": notes, "name": obj.get("name") or ""}
    # 通用清单
    ver = str(obj.get("version", "") or "").lstrip("vV")
    if not ver:
        return None
    out = {
        "version": ver,
        "url": str(obj.get("url", "") or ""),
        "notes": str(obj.get("notes", "") or "").strip(),
        "name": str(obj.get("name", "") or ""),
    }
    # 自建清单也可以直接带蓝奏云镜像（键名与内置镜像表一致），省去改代码
    for k in ("lanzou_setup", "lanzou_portable"):
        v = str(obj.get(k, "") or "").strip()
        if v:
            out[k] = v
    return out



def clean_query_text(s: str) -> str:
    s = re.sub(r"[\(\)（）\[\]【】].*?[\)\)）\]\]】]", "", s or "")
    s = re.sub(r"\b(feat|ft|live|mv|伴奏|instrumental)\b.*$", "", s, flags=re.I)
    return s.strip()


def norm_text(s: str) -> str:
    return re.sub(r"[\W_]+", "", (s or "").lower())


# 制作名单行：角色 + 冒号（「作词：李荣浩」「小提琴：须磨和声」「编曲 Arrangement：xxx」）。
# 必须带冒号（或整行只有角色名），这样「鼓起勇气」这类正常歌词不会被当成「鼓」的名单。
_CREDIT_ROLE = (r"作?词|作曲|词曲|编曲|和声|合声|合唱|混音|录音|母带|制作人?|监制|出品人?|版权|发行|推广|"
                r"策划|文案|原唱|翻唱|吉他|贝斯|鼓|键盘|钢琴|小提琴|大提琴|中提琴|弦乐|笛子?|箫|古筝|"
                r"二胡|琵琶|打击乐|配唱|和音|伴唱|人声|后期|统筹|企划|录音师|演唱|视觉|封面|设计|导演|"
                r"曲|OP|SP|Lyricist|Composer|Arranger|Producer|Mixing|Mastering|Guitar|Bass|Drums|"
                r"Piano|Strings|Violin|Cello|"
                # 致谢 / 出品 / 宣发一类（「特别支持：中村光雄」）
                r"特别支持|特别鸣谢|特别感谢|鸣谢|致谢|感谢|特别出演|特别嘉宾|联合出品|出品公司|发行公司|"
                r"音乐总监|总策划|执行制作|制作助理|音乐制作|后期制作|录音室|录音棚|混音室|母带室|"
                r"制作统筹|企划统筹|宣发|宣传|经纪|艺人|造型|摄影|化妆|发型|指挥|乐团|合唱团|演奏|"
                r"独奏|配乐|音效|平面|插画|总监|统筹")

_CREDIT_SUFFIX = r"(?:工程师|工程|师|助理|人|编写|编辑|制作|总监|指导|老师)"

_CREDIT_PAT = re.compile(
    r"^\s*(?:" + _CREDIT_ROLE + r")(?:\s*" + _CREDIT_SUFFIX + r")?(?:\s+[A-Za-z.&'\-]+)*\s*[:：]"
    r"|^\s*(?:" + _CREDIT_ROLE + r")(?:\s*" + _CREDIT_SUFFIX + r")?\s*$", re.I)

# 宽松版（无冒号也认），只在歌曲开头十几秒内使用：
# "lyric / compos / written" 这些英文词本身可能出现在正常歌词里，不能全局启用。
_CREDIT_LOOSE = re.compile(
    r"^\s*(词|曲|作词|作曲|编曲|和声|合声|合唱|混音|录音|母带|制作|监制|OP|SP|"
    r"吉他|贝斯|鼓|键盘|出品|版权|发行|推广|策划|文案|原唱|翻唱)"
    r"|lyric|compos|written|arrang|copyright", re.I)

# 信息行：标题行「歌手 - 歌名」、版权/免责声明、歌词来源水印、制作名单。
# 借鉴 Lyricify-Lyrics-Helper 的「识别并处理信息行（标题行）」。
_INFO_PAT = re.compile(r"未经.{0,8}(许可|允许)|不得翻唱|不得用于|翻录|著作权|版权|本歌词由|歌词制作|"
                       r"酷狗音乐|QQ音乐|网易云音乐|纯音乐请欣赏|^.{0,24}\s-\s.{0,32}$")


def is_info_line(text: str) -> bool:
    """是否为信息行（不是真正要唱的歌词）"""
    t = (text or "").strip()
    if not t:
        return False
    return bool(_INFO_PAT.search(t)) or bool(_CREDIT_PAT.search(t))



def fetch_qq_search(query: str, timeout: float = 6.0):
    """在QQ音乐搜索，返回 [{mid, albummid, name, singer}, ...]"""
    payload = json.dumps({
        "req": {
            "method": "DoSearchForQQMusicDesktop",
            "module": "music.search.SearchCgiService",
            "param": {"search_type": 0, "query": query, "page_num": 1, "num_per_page": 10},
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://u.y.qq.com/cgi-bin/musicu.fcg", data=payload,
        headers={"User-Agent": BROWSER_UA, "Referer": "https://y.qq.com/",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    items = (((data.get("req") or {}).get("data") or {}).get("body") or {}).get("song") or {}
    results = []
    for it in items.get("list") or []:
        album = it.get("album") or {}
        sg = it.get("singer") or []
        results.append({
            "mid": it.get("mid") or "",
            "albummid": album.get("mid") or "",
            "name": it.get("name") or "",
            "singer": (sg[0].get("name") if sg and isinstance(sg, list) else "") or "",
        })
    return results


def _b64_text(v):
    try:
        return base64.b64decode(v).decode("utf-8", "ignore") if v else ""
    except Exception:
        return ""


def fetch_qq_lyric(songmid: str, timeout: float = 6.0):
    """通过 songmid 拿 (原文 LRC, 翻译 LRC)（无登录态，绝大多数歌曲可取）"""
    url = ("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?"
           "pcachetime=%d&songmid=%s&g_tk=5381&loginUin=0&hostUin=0&format=json"
           "&inCharset=utf8&outCharset=utf-8&notice=0&platform=yqq.json&needNewCode=0"
           % (int(time.time() * 1000), urllib.parse.quote(songmid)))
    text = http_get(url, headers={"Referer": "https://y.qq.com/"},
                    timeout=timeout).decode("utf-8", "ignore")
    m = re.match(r"^\w+\((.*)\)\s*$", text, re.S)
    if m:
        text = m.group(1)
    data = json.loads(text)
    if data.get("retcode") not in (0, None) or not data.get("lyric"):
        return None, ""
    return _b64_text(data.get("lyric")), _b64_text(data.get("trans"))


# ---------------- 网易云 ----------------

_WEAPI_PUB_E = "010001"
_WEAPI_PUB_N = ("00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876a"
                "ea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05"
                "c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e28"
                "9dc6935b3ece0462db0a22b8e7")
_WEAPI_IV = b"0102030405060708"
_WEAPI_PRESET_KEY = "0CoJUm6Qyw8W8jud"


def _weapi_post(path: str, payload: dict, timeout: float = 6.0):
    """网易云 weapi 加密 POST（AES-CBC x2 + RSA 无填充），返回 JSON"""
    from Crypto.Cipher import AES      # 延迟导入：只有真走网易云加密接口才付这 ~80ms

    def aes(text: str, key: str) -> str:
        pad = 16 - len(text) % 16
        data = (text + chr(pad) * pad).encode("utf-8")
        cipher = AES.new(key.encode("ascii"), AES.MODE_CBC, _WEAPI_IV)
        return base64.b64encode(cipher.encrypt(data)).decode("ascii")

    rnd = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(16))
    params = aes(aes(json.dumps(payload, separators=(",", ":")), _WEAPI_PRESET_KEY), rnd)
    m = int.from_bytes(rnd[::-1].encode("ascii"), "big")
    enc_sec_key = ("%x" % pow(m, int(_WEAPI_PUB_E, 16), int(_WEAPI_PUB_N, 16))).zfill(256)
    body = urllib.parse.urlencode({"params": params, "encSecKey": enc_sec_key}).encode("ascii")
    req = urllib.request.Request(
        "https://music.163.com" + path, data=body,
        headers={"User-Agent": BROWSER_UA, "Referer": "https://music.163.com/",
                 "Content-Type": "application/x-www-form-urlencoded",
                 "Cookie": "os=pc; appver=2.9.7"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def netease_pic_id_to_url(pic_id) -> str:
    """网易云图片 id -> CDN URL（经典加密 id 算法，无需鉴权）"""
    if not pic_id:
        return ""
    try:
        magic = bytearray(b"3go8&$8*3*3h0k(2)2")
        sid = bytearray(str(pic_id).encode("ascii"))
        for i in range(len(sid)):
            sid[i] ^= magic[i % len(magic)]
        enc = base64.b64encode(hashlib.md5(bytes(sid)).digest())
        enc = enc.replace(b"/", b"_").replace(b"+", b"-").decode("ascii")
        return "https://p3.music.126.net/%s/%s.jpg?param=500y500" % (enc, pic_id)
    except Exception:
        return ""


def fetch_netease_search(query: str, timeout: float = 6.0):
    """网易云搜索，返回 [{id, name, singer, pic_url}, ...]"""
    songs = []
    if _crypto_ready():
        try:
            data = _weapi_post("/weapi/search/get",
                               {"s": query, "type": 1, "offset": 0, "limit": 20,
                                "csrf_token": ""}, timeout=timeout)
            songs = (data.get("result") or {}).get("songs") or []
        except Exception:
            log("netease weapi search failed, fallback:\n" + traceback.format_exc())
    if not songs:
        songs = fetch_netease_search_plain(query, timeout=timeout)
    results = []
    for it in songs:
        artists = it.get("artists") or []
        album = it.get("album") or {}
        pic = album.get("picUrl") or netease_pic_id_to_url(album.get("picId") or album.get("pic_str"))
        if pic:
            pic = pic.replace("http://", "https://")
            if "?" not in pic:
                pic += "?param=500y500"
        results.append({
            "id": str(it.get("id") or ""),
            "name": it.get("name") or "",
            "singer": (artists[0].get("name") if artists else "") or "",
            "pic_url": pic,
        })
    return results


def fetch_netease_search_plain(query: str, timeout: float = 6.0):
    """老版网易云搜索接口（未加密；未登录时排序差，仅作降级）"""
    body = urllib.parse.urlencode(
        {"s": query, "type": 1, "offset": 0, "limit": 20, "total": "true"}).encode("utf-8")
    req = urllib.request.Request(
        "https://music.163.com/api/search/get/web", data=body,
        headers={"User-Agent": BROWSER_UA, "Referer": "https://music.163.com/",
                 "Content-Type": "application/x-www-form-urlencoded",
                 "Cookie": "os=pc; appver=2.9.7"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    return (data.get("result") or {}).get("songs") or []


def fetch_netease_lyric(song_id: str, timeout: float = 6.0):
    """网易云歌词老接口，返回 (原文 LRC, 翻译 LRC)"""
    url = "https://music.163.com/api/song/lyric?id=%s&lv=1&kv=1&tv=-1" % urllib.parse.quote(song_id)
    data = json.loads(http_get(url, headers={"Referer": "https://music.163.com/"},
                               timeout=timeout).decode("utf-8", "ignore"))
    return (((data.get("lrc") or {}).get("lyric")) or None,
            ((data.get("tlyric") or {}).get("lyric")) or "")


def fetch_netease_lyric_full(song_id: str, timeout: float = 6.0):
    """网易云歌词：优先逐字 YRC，返回 (lines, words, trans)"""
    if _crypto_ready():
        try:
            data = _weapi_post("/weapi/song/lyric/v1",
                               {"id": song_id, "cv": 4797911, "lv": 0, "kv": 0, "tv": 0,
                                "rv": 0, "yv": 0, "ytv": 0, "yrv": 0, "csrf_token": ""},
                               timeout=timeout)
            tlyric = (data.get("tlyric") or {}).get("lyric") or ""
            trans = parse_trans(tlyric) if tlyric else []
            yrc = (data.get("yrc") or {}).get("lyric") or ""
            if yrc:
                lines, words = parse_yrc(yrc)
                if lines:
                    return lines, words, trans
            lrc = (data.get("lrc") or {}).get("lyric") or ""
            if lrc:
                pl, pw = parse_lrc(lrc)
                return pl, pw, trans
        except Exception:
            log("netease lyric/v1 failed:\n" + traceback.format_exc())
    try:
        lrc, tlyric = fetch_netease_lyric(song_id, timeout=timeout)
        if lrc:
            pl, pw = parse_lrc(lrc)
            return pl, pw, (parse_trans(tlyric) if tlyric else [])
    except Exception:
        pass
    return [], {}, []


_LRCLIB_UA = "Desktop-sing/1.0"


def fetch_lrclib_candidates(title: str, artist: str, timeout: float = 6.0):
    """LRCLIB 候选（免费、无需鉴权）：返回 [{lines, words, trans, duration, raw, name, artist}]

    LRCLIB 是社区库，海外/独立音乐的覆盖率明显好于国内平台，放进来做候选更稳。
    timeout 由调用方按需收紧（它是常被墙/慢的那个源，不能让整条链路等它）。
    """
    out = []
    try:
        url = ("https://lrclib.net/api/search?track_name=%s&artist_name=%s"
               % (urllib.parse.quote(title), urllib.parse.quote(artist)))
        data = json.loads(http_get(url, headers={"User-Agent": _LRCLIB_UA},
                                   timeout=timeout).decode("utf-8", "ignore"))
    except Exception:
        log("LRCLIB search failed: " + traceback.format_exc())
        return out
    for it in (data or [])[:5]:
        synced = it.get("syncedLyrics") or ""
        if not synced:
            continue                      # 纯文本（无时间轴）对本程序没用
        try:
            lines, words = parse_lrc(synced)
        except Exception:
            continue
        if not lines:
            continue
        out.append({"lines": lines, "words": words, "trans": [],
                    "duration": float(it.get("duration") or 0), "raw": synced,
                    "name": it.get("trackName") or title,
                    "artist": it.get("artistName") or artist})
    return out


def fetch_lrclib_lyric(title: str, artist: str):
    """LRCLIB 兜底（保留旧接口）：返回最优候选的原始文本，失败返回 None"""
    cands = fetch_lrclib_candidates(title, artist)
    if not cands:
        return None
    # 带逐字增强标签（<mm:ss.xx>）的版本优先
    for c in cands:
        if c["words"] and "<" in c["raw"]:
            return c["raw"]
    return max(cands, key=lambda c: score_lyrics(c["lines"], c["words"], c["trans"],
                                                 c["duration"]))["raw"]


# ---------------- 酷狗（KRC 逐字） ----------------
# 借鉴 Lyricify-Lyrics-Helper（Apache-2.0）的 Decrypter/Krc 与 Providers/Web/Kugou：
# 酷狗把逐字歌词放在 KRC 里，base64 后整体异或再 zlib 压缩。

_KRC_XOR_KEY = bytes([0x40, 0x47, 0x61, 0x77, 0x5E, 0x32, 0x74, 0x47,
                      0x51, 0x36, 0x31, 0x2D, 0xCE, 0xD2, 0x6E, 0x69])
_KRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_KRC_SYL = re.compile(r"<(\d+),(\d+),\d+>([^<]*)")


def decrypt_krc(b64_text: str):
    """KRC 密文 -> 明文 KRC（base64 → 去 4 字节头 → 异或 → zlib → 去掉首字符）"""
    raw = base64.b64decode(b64_text)
    if raw[:4] not in (b"krc1", b"KRC1"):
        # 少数接口会把明文直接塞进来，头不符时按未加密处理
        if raw[:1] in (b"[", b"\xef"):
            return raw.decode("utf-8", "ignore")
        raw = raw[4:]
    else:
        raw = raw[4:]
    buf = bytearray(raw)
    for i in range(len(buf)):
        buf[i] ^= _KRC_XOR_KEY[i % len(_KRC_XOR_KEY)]
    text = zlib.decompress(bytes(buf)).decode("utf-8", "ignore")
    return text[1:] if text[:1] in ("\ufeff", "\x00") else text


def _krc_translation(text: str):
    """KRC 里的 [language:base64] 是翻译（每行一条，"//" 表示该行无翻译）"""
    m = re.search(r"\[language:([^\]]+)\]", text)
    if not m:
        return {}
    try:
        data = json.loads(base64.b64decode(m.group(1)).decode("utf-8", "ignore"))
        for content in data.get("content") or []:
            if content.get("type") == 1:            # type=1 为译文
                rows = [r[0] for r in (content.get("lyricContent") or [])]
                return {i: t for i, t in enumerate(rows) if t and t != "//"}
    except Exception:
        pass
    return {}


def parse_krc(text: str):
    """酷狗 KRC 逐字歌词 -> (lines, words, trans)

    KRC 行形如 `[行起点ms,行时长ms]<字相对起点ms,字时长ms,0>字<...>`，
    字的时间是**相对行首**的偏移；trans 来自 [language:] 里的逐行译文。
    """
    if not text:
        return [], {}, []
    offset_ms = 0.0
    m = re.search(r"^\[offset:\s*([+-]?\d+)\s*\]", text, re.M)
    if m:
        offset_ms = float(m.group(1))
    trans_map = _krc_translation(text)
    rows = []
    for raw in text.splitlines():
        raw = raw.strip()
        mm = _KRC_LINE.match(raw)
        if not mm:
            continue
        start = int(mm.group(1)) / 1000.0
        body = mm.group(3)
        chunks = [[start + int(a) / 1000.0, max(0.05, int(b) / 1000.0), c]
                  for a, b, c in _KRC_SYL.findall(body)]
        chunks = _trim_word_chunks([[t, d, c] for t, d, c in chunks if c])
        if not chunks:
            continue
        txt = "".join(c for _, _, c in chunks)
        if not txt.strip():
            continue
        rows.append((start, txt, chunks, raw))
    rows.sort(key=lambda r: r[0])
    rows = [r for r in rows
            if not is_info_line(r[1])
            and not (r[0] < 14.0 and (not r[1].strip() or _CREDIT_LOOSE.search(r[1])))]
    lines = [[max(0.0, t - offset_ms / 1000.0), txt] for t, txt, _c, _r in rows]
    words = {}
    for i, (t, txt, chunks, _r) in enumerate(rows):
        if len(chunks) >= 2:
            shift = offset_ms / 1000.0
            words[i] = [[max(0.0, a - shift), b, c] for a, b, c in chunks]
    trans = []
    for i, (t, _txt, _c, _r) in enumerate(rows):
        tt = trans_map.get(i)
        if tt:
            trans.append([max(0.0, t - offset_ms / 1000.0), tt])
    return lines, words, trans


def fetch_kugou_search(query: str, timeout: float = 6.0):
    """酷狗搜索：返回 [{hash, duration(秒), name, singer}]（歌词接口要用 hash+时长对齐）"""
    url = ("http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword=%s"
           "&page=1&pagesize=10&showtype=1" % urllib.parse.quote(query))
    data = json.loads(http_get(url, timeout=timeout).decode("utf-8", "ignore"))
    out = []
    for it in ((data.get("data") or {}).get("info") or []):
        out.append({
            "hash": it.get("hash") or "",
            "duration": int(it.get("duration") or 0),
            "name": it.get("songname") or "",
            "singer": it.get("singername") or "",
        })
    return out


def fetch_kugou_lyric(name: str, duration: int, file_hash: str, timeout: float = 6.0):
    """酷狗歌词：取候选里的 KRC 逐字 -> (lines, words, trans)；失败退回 LRC 文本"""
    url = ("https://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword=%s&duration=%d&hash=%s"
           % (urllib.parse.quote(name), duration, file_hash))
    data = json.loads(http_get(url, timeout=timeout).decode("utf-8", "ignore"))
    for cand in (data.get("candidates") or [])[:3]:
        try:
            dl = json.loads(http_get(
                "https://lyrics.kugou.com/download?ver=1&client=pc&id=%s&accesskey=%s&fmt=krc&charset=utf8"
                % (cand.get("id"), cand.get("accesskey")), timeout=timeout).decode("utf-8", "ignore"))
            if dl.get("status") not in (200, 0, None) or not dl.get("content"):
                continue
            krc = decrypt_krc(dl["content"])
        except Exception:
            log("kugou krc failed:\n" + traceback.format_exc())
            continue
        lines, words, trans = parse_krc(krc)
        if lines:
            return lines, words, trans
    return [], {}, []


# ---------------- 歌词解析 ----------------

_LRC_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_LRC_WORD = re.compile(r"<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>")
_WORD_TAG = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?>")
_LRC_META = re.compile(r"^\[(ti|ar|al|by|offset|re|ve|hash|total|kana?|tool|length)\s*:", re.I)
_YRC_LINE = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_YRC_WORD = re.compile(r"\((\d+),(\d+),\d+\)([^(]*)")


def _tag_seconds(m) -> float:
    frac = m.group(3) or "0"
    return int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))


def _split_word_tags(content: str):
    """增强 LRC 的 <mm:ss.xx>词 标签 -> [[t, dur, 词块]...]；无标签返回 None"""
    ms = list(_WORD_TAG.finditer(content))
    if not ms:
        return None
    chunks = []
    for i, m in enumerate(ms):
        t = _tag_seconds(m)
        end = ms[i + 1].start() if i + 1 < len(ms) else len(content)
        piece = content[m.end():end].strip()
        dur = (_tag_seconds(ms[i + 1]) - t) if i + 1 < len(ms) else 0.6
        if piece:
            chunks.append([max(0.0, t), max(0.15, dur), piece])
    return chunks or None


def _trim_word_chunks(chunks):
    while chunks and not chunks[0][2].strip():
        chunks.pop(0)
    while chunks and not chunks[-1][2].strip():
        chunks.pop()
    return chunks


def parse_lrc(text: str):
    """LRC -> (lines, words)；words 为逐字增强标签（存在时）"""
    if not text:
        return [], {}
    offset_ms = 0.0
    m = re.search(r"^\[offset\s*:\s*([+-]?\d+)\s*\]", text, re.I | re.M)
    if m:
        offset_ms = float(m.group(1))
    rows = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or _LRC_META.match(raw):
            continue
        stamps = [(int(mm) * 60 + int(ss) + (int(frac) / (10 ** len(frac)) if frac else 0))
                  for mm, ss, frac in _LRC_TIME.findall(raw)]
        if not stamps:
            continue
        rest = _LRC_TIME.sub("", raw).strip()
        chunks = _split_word_tags(rest)
        if chunks:
            txt = "".join(c for _, _, c in chunks)
        else:
            txt = _LRC_WORD.sub("", rest).strip()
        for t in stamps:
            rows.append((max(0.0, t - offset_ms / 1000.0), txt, chunks if len(stamps) == 1 else None))
    rows.sort(key=lambda r: r[0])
    rows = [r for r in rows if not is_info_line(r[1])
            and not (r[0] < 14.0 and (not r[1].strip() or _CREDIT_LOOSE.search(r[1])))]
    lines = [[t, txt] for t, txt, _c in rows]
    words = {}
    for i, (_t, _txt, c) in enumerate(rows):
        if c and len(c) >= 2:
            words[i] = c
    return lines, words


def parse_yrc(text: str):
    """网易云 YRC 逐字歌词 -> (lines, words)"""
    if not text:
        return [], {}
    rows = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("{"):
            continue
        m = _YRC_LINE.match(raw)
        if not m:
            continue
        start = int(m.group(1)) / 1000.0
        dur = int(m.group(2)) / 1000.0
        chunks = [[int(a) / 1000.0, max(0.05, int(b) / 1000.0), c]
                  for a, b, c in _YRC_WORD.findall(m.group(3))]
        chunks = _trim_word_chunks(chunks)
        if not chunks:
            chunks = [[start, dur, ""]]
        txt = "".join(c for _, _, c in chunks)
        rows.append((start, txt, chunks))
    rows.sort(key=lambda r: r[0])
    rows = [r for r in rows if not is_info_line(r[1])
            and not (r[0] < 14.0 and (not r[1].strip() or _CREDIT_LOOSE.search(r[1])))]
    lines = [[t, txt] for t, txt, _c in rows]
    words = {i: c for i, (_t, _txt, c) in enumerate(rows) if len(c) >= 2}
    return lines, words


def parse_trans(text: str):
    """翻译 / 音译 LRC -> [[t, 文本]...]（与原文同时间轴，按行匹配）"""
    if not text:
        return []
    rows = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or _LRC_META.match(raw):
            continue
        stamps = [(int(mm) * 60 + int(ss) + (int(frac) / (10 ** len(frac)) if frac else 0))
                  for mm, ss, frac in _LRC_TIME.findall(raw)]
        if not stamps:
            continue
        txt = _LRC_WORD.sub("", _LRC_TIME.sub("", raw)).strip()
        if not txt:
            continue
        for t in stamps:
            rows.append((max(0.0, t), txt))
    rows.sort(key=lambda r: r[0])
    return [[t, txt] for t, txt in rows]


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.md5(key.encode("utf-8")).hexdigest() + ".json")


# ---------------- 歌词格式识别 / 时间轴工具 ----------------
# 借鉴 Lyricify-Lyrics-Helper 的 TypeHelper（自动识别）与 OffsetHelper（整体偏移）。

LYRIC_FORMATS = {
    "lrc": "LRC 逐行",
    "yrc": "网易云 YRC 逐字",
    "krc": "酷狗 KRC 逐字",
    "unsynced": "未同步纯文本",
}

_LRC_STAMP = re.compile(r"^\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]", re.M)
_YRC_STAMP = re.compile(r"^\[\d+,\d+\]\(\d+,\d+,\d+\)", re.M)
_KRC_STAMP = re.compile(r"^\[\d+,\d+\]<\d+,\d+,\d+>", re.M)


def detect_lyric_format(text: str) -> str:
    """按特征识别歌词格式（无需声明类型即可解析，对应 Lyricify 的 TypeHelper）"""
    if not text:
        return "unsynced"
    if _KRC_STAMP.search(text) or "[language:" in text:
        return "krc"
    if _YRC_STAMP.search(text):
        return "yrc"
    if _LRC_STAMP.search(text):
        return "lrc"
    return "unsynced"


def parse_lyrics_auto(text: str):
    """自动识别格式并解析，返回 (lines, words, trans)"""
    fmt = detect_lyric_format(text)
    if fmt == "krc":
        return parse_krc(text)
    if fmt == "yrc":
        lines, words = parse_yrc(text)
        return lines, words, []
    if fmt == "lrc":
        lines, words = parse_lrc(text)
        return lines, words, []
    return [], {}, []


def offset_lines(lines, words=None, trans=None, seconds: float = 0.0):
    """整条时间轴平移 seconds（正=歌词更晚出现），对应 Lyricify 的 OffsetHelper"""
    if not seconds:
        return lines, words or {}, trans or []
    new_lines = [[max(0.0, t + seconds), txt] for t, txt in lines]
    new_words = {i: [[max(0.0, a + seconds), d, c] for a, d, c in chunks]
                 for i, chunks in (words or {}).items()}
    new_trans = [[max(0.0, t + seconds), txt] for t, txt in (trans or [])]
    return new_lines, new_words, new_trans


def downgrade_to_lines(lines, trans=None):
    """逐字 -> 逐行（丢掉 word 层），用于不支持逐字的场景"""
    return [list(r) for r in lines], {}, [list(r) for r in (trans or [])]


def generate_lrc(lines, trans=None) -> str:
    """生成标准 LRC 文本（导出 / 与外部播放器互通）"""
    def stamp(t: float) -> str:
        t = max(0.0, float(t))
        return "[%02d:%05.2f]" % (int(t // 60), t % 60)

    out = []
    if trans:
        seen = {}
        for t, txt in trans:
            seen.setdefault(round(float(t), 2), txt)
        for t, txt in lines:
            out.append("%s%s" % (stamp(t), txt))
            tt = seen.get(round(float(t), 2))
            if tt:
                out.append("%s%s" % (stamp(t), tt))
    else:
        for t, txt in lines:
            out.append("%s%s" % (stamp(t), txt))
    return "\n".join(out)


# ---------------- 歌词质量评分 / 清洗 ----------------
# 借鉴 Lyricify 的「智能匹配引擎」：多源候选先打分再择优，而不是先到先得；
# 以及 Lyrics Optimization：去空行 / 去制作名单 / 同时间戳去重 / 繁简转换。

_EMPTY_RE = re.compile(r"^[\s\-–—~·.、,，!！?？…]*$")


def score_lyrics(lines, words=None, trans=None, duration: float = 0.0) -> int:
    """候选质量分：有逐字 +30、有翻译 +12、行数（封顶 25）、末行贴合歌曲时长 +15

    宁可多试一个源拿到带逐字时间轴的版本，也不要先用普通 LRC 顶上。
    """
    if not lines:
        return -1
    score = 0
    if words:
        score += 30
    if trans:
        score += 12
    score += min(len(lines), 25)
    if duration and duration > 0:
        last = max(float(r[0]) for r in lines)
        if last <= duration + 8:                       # 末行远超时长 = 大概率串词
            score += 5
        if abs(last - duration) <= max(12.0, duration * 0.12):
            score += 10
    return score


def clean_lyrics(lines, words=None, trans=None, keep_info: bool = False):
    """清洗歌词，返回 (lines, words, trans)

    - 丢弃空行 / 纯符号行；
    - 丢弃信息行（版权声明、歌词水印、"歌手 - 歌名"标题行）；
    - 同一时间戳的重复行只保留第一条（多歌手版本常见）；
    - 按时间重新排序；words 的行号随重建后的 lines 重新编号。
    """
    if not lines:
        return [], {}, []
    src_words = words or {}
    kept, seen = [], set()
    for i, row in enumerate(lines):
        t = float(row[0])
        txt = str(row[1] if len(row) > 1 else "").strip()
        if not txt or _EMPTY_RE.match(txt):
            continue
        if not keep_info and is_info_line(txt):
            continue
        k = round(t, 2)
        if k in seen:
            continue
        seen.add(k)
        kept.append((i, t, txt))
    kept.sort(key=lambda r: r[1])
    new_lines = [[t, txt] for _i, t, txt in kept]
    new_words = {}
    for n, (i, _t, _txt) in enumerate(kept):
        if i in src_words:
            new_words[n] = [list(c) for c in src_words[i]]
    new_trans = []
    for t, txt in (trans or []):
        s = str(txt or "").strip()
        if not s or _EMPTY_RE.match(s) or is_info_line(s):
            continue
        new_trans.append([float(t), s])
    return new_lines, new_words, new_trans


# ---------------- 繁简转换（Lyricify Lyrics Optimization 的可选能力） ----------------
# 内置「高频字」表，覆盖歌词中最常见的繁体字；完整表可放在
# %APPDATA%\Desktop-sing\t2s.tsv（每行「繁体<TAB>简体」，支持一行多组），优先使用它。

T2S_TABLE_PATH = os.path.join(CFG_DIR, "t2s.tsv")

T2S_PARTIAL = """
這这 們们 說说 對对 時时 會会 個个 來来 為为 爲为 與与 國国 學学 產产 東东 車车 馬马 鳥鸟 魚鱼
龍龙 風风 雲云 電电 話话 語语 讀读 寫写 聽听 見见 覺觉 讓让 誰谁 麼么 麽么 樣样 過过 還还 進进 邊边
際际 現现 實实 無无 愛爱 夢梦 淚泪 傷伤 憶忆 記记 認认 識识 願愿 應应 該该 燈灯 陽阳 陰阴 間间 門门
問问 開开 關关 長长 張张 後后 從从 眾众 兒儿 頭头 發发 髮发 隻只 臺台 萬万 億亿 絲丝 兩两 嚴严 喪丧
樂乐 習习 書书 買买 亂乱 爭争 於于 虧亏 亞亚 僅仅 倉仓 儀仪 價价 優优 傳传 偉伟 體体 餘余 侶侣 俠侠
倆俩 債债 傾倾 儲储 黨党 蘭兰 興兴 養养 獸兽 內内 軍军 農农 沖冲 決决 況况 凍冻 淨净 涼凉 減减 鳳凤
憑凭 凱凯 擊击 創创 別别 剎刹 製制 則则 剛刚 劍剑 劉刘 動动 務务 勳勋 勢势 勵励 勸劝 辦办 協协 單单
賣卖 衛卫 卻却 廠厂 廳厅 歷历 曆历 壓压 厭厌 縣县 參参 雙双 變变 疊叠 號号 嘆叹 團团 園园 圍围 圖图
圓圆 聖圣 場场 壞坏 塊块 堅坚 壇坛 墳坟 墜坠 壘垒 聲声 殼壳 處处 備备 復复 複复 夾夹 奪夺 獎奖 奮奋
妝妆 婦妇 媽妈 嬌娇 娛娱 嬰婴 嬋婵 寧宁 寶宝 審审 宮宫 寬宽 賓宾 尋寻 導导 壽寿 將将 爾尔 塵尘 嘗尝
盡尽 儘尽 層层 屬属 歲岁 崗岗 島岛 嶺岭 峽峡 嶄崭 巔巅 幣币 師师 帳帐 幟帜 帶带 幫帮 廣广 莊庄 慶庆
廬庐 廟庙 廢废 棄弃 鬧闹 閣阁 異异 彎弯 彈弹 強强 歸归 當当 錄录 徹彻 徑径 禦御 懷怀 態态 憐怜 總总
戀恋 懇恳 惡恶 惱恼 悅悦 懸悬 驚惊 懼惧 慘惨 懲惩 憊惫 慚惭 慣惯 懾慑 懶懒 戲戏 戰战 戶户 撲扑 執执
擴扩 掃扫 揚扬 擾扰 撫抚 拋抛 護护 報报 擔担 擬拟 攏拢 擁拥 撥拨 擇择 掛挂 摯挚 損损 換换 據据 擄掳
摻掺 攬揽 撐撑 擻擞 敵敌 數数 斂敛 斬斩 斷断 舊旧 曠旷 曇昙 晝昼 顯显 曬晒 曉晓 暈晕 晉晋 機机 殺杀
雜杂 權权 條条 楊杨 極极 構构 槍枪 楓枫 櫃柜 標标 棧栈 棟栋 樹树 檔档 橋桥 檢检 樓楼 歡欢 歐欧 殘残
殞殒 毀毁 氣气 漢汉 湯汤 洶汹 溝沟 沒没 淪沦 濘泞 瀉泻 澤泽 潔洁 灑洒 淺浅 漿浆 澆浇 濁浊 測测 濟济
渾浑 濃浓 湧涌 塗涂 濤涛 澇涝 渦涡 潤润 澀涩 澱淀 濕湿 潰溃 滾滚 滿满 濾滤 濫滥 濱滨 灘滩 滯滞 潛潜
瀾澜 湊凑 滅灭 靈灵 災灾 燦灿 爐炉 點点 煉炼 爛烂 煙烟 煩烦 燒烧 燙烫 熱热 煥焕 爺爷 牘牍 牽牵 犧牺
猶犹 狽狈 獰狞 獨独 狹狭 獅狮 獄狱 獵猎 豬猪 貓猫 蝟猬 獻献 瑪玛 環环 瑣琐 瓊琼 甕瓮 畫画 暢畅 療疗
瘧疟 瘍疡 瘡疮 瘋疯 癰痈 痙痉 癢痒 瘓痪 癡痴 癱瘫 癮瘾 癲癫 皚皑 皺皱 盜盗 盤盘 監监 蓋盖 睜睁 瞞瞒
磯矶 礬矾 礦矿 碼码 磚砖 硯砚 礙碍 禮礼 禱祷 祿禄 離离 種种 積积 稱称 穢秽 穩稳 窮穷 竊窃 竅窍 窯窑
竄窜 窩窝 窺窥 豎竖 競竞 筍笋 筆笔 籠笼 築筑 篩筛 篳筚 籌筹 簽签 簡简 籮箩 糞粪 糧粮 緊紧 糾纠 紀纪
紉纫 緯纬 純纯 紗纱 綱纲 納纳 縱纵 紛纷 紙纸 紐纽 線线 練练 組组 細细 織织 終终 絆绊 紹绍 經经 綁绑
絨绒 結结 繞绕 繪绘 給给 絡络 絕绝 絞绞 統统 繼继 績绩 緒绪 續续 繩绳 維维 綿绵 繃绷 綜综 綠绿 綴缀
纜缆 緝缉 緞缎 緩缓 編编 緣缘 縛缚 縫缝 纏缠 縮缩 繳缴 網网 羅罗 罰罚 罷罢 羨羡 翹翘 恥耻 聶聂 聾聋
職职 聯联 聰聪 肅肃 腸肠 膚肤 腫肿 脹胀 脅胁 膽胆 勝胜 膠胶 脈脉 臟脏 髒脏 腦脑 膿脓 臉脸 臘腊 膩腻
騰腾 輿舆 艦舰 艙舱 艱艰 蘆芦 蘇苏 蘋苹 範范 莖茎 繭茧 薦荐 藥药 榮荣 萊莱 蓮莲 獲获 穫获 瑩莹 蘿萝
營营 蕭萧 薩萨 蔥葱 藍蓝 薊蓟 驀蓦 薔蔷 藹蔼 蘊蕴 藪薮 蘚藓 虜虏 慮虑 虛虚 蟲虫 虯虬 雖虽 蝕蚀 蟻蚁
蠶蚕 蠔蚝 蠻蛮 蠟蜡 蠅蝇 蟬蝉 蠍蝎 蠑蝾 銜衔 補补 襯衬 襖袄 裝装 襠裆 褲裤 觀观 規规 覓觅 視视 覽览
觴觞 觸触 訂订 計计 討讨 訓训 議议 訊讯 講讲 諱讳 訝讶 訥讷 許许 訛讹 論论 訟讼 諷讽 設设 訪访 訣诀
證证 評评 詛诅 訴诉 診诊 詞词 譯译 試试 詩诗 誠诚 誕诞 詢询 詳详 誡诫 誣诬 誤误 誘诱 誦诵 請请 諸诸
諾诺 課课 調调 諒谅 談谈 誼谊 謀谋 謊谎 諧谐 謂谓 諺谚 謎谜 謝谢 謠谣 謗谤 謙谦 謹谨 謬谬 譚谭 譜谱
譴谴 穀谷 貝贝 貞贞 負负 貢贡 財财 責责 賢贤 敗败 賬账 貨货 質质 販贩 貪贪 貧贫 貶贬 購购 貫贯 賤贱
貼贴 貴贵 貸贷 貿贸 費费 賀贺 貽贻 賊贼 賈贾 賄贿 賃赁 賂赂 贓赃 資资 賑赈 賒赊 賦赋 賭赌 贖赎 賞赏
賜赐 賠赔 賴赖 賺赚 賽赛 讚赞 贊赞 贈赠 贍赡 贏赢 贛赣 趙赵 趕赶 趨趋 躍跃 蹌跄 蹺跷 踐践 躋跻 踴踊
躊踌 蹤踪 躡蹑 蹣蹒 軋轧 軌轨 軒轩 轉转 輪轮 軟软 轟轰 軸轴 輕轻 載载 轎轿 較较 輻辐 輯辑 輸输 轄辖
輾辗 轆辘 轍辙 辮辫 達达 遷迁 邁迈 運运 這这 遠远 違违 連连 遲迟 跡迹 蹟迹 遞递 邏逻 遺遗 遙遥 鄧邓
郵邮 鄰邻 鬱郁 鄭郑 醞酝 醬酱 釀酿 釋释 裏里 裡里 鑒鉴 鑑鉴 針针 釘钉 釣钓 鈣钙 鈍钝 鈔钞 鐘钟 鍾钟
鈉钠 鋼钢 鑰钥 欽钦 鉤钩 錢钱 鉗钳 鑽钻 鐵铁 鈴铃 鉛铅 鉚铆 銅铜 鋁铝 鎧铠 銘铭 銀银 鋪铺 鏈链 銷销
鎖锁 鍋锅 鏽锈 鋒锋 銳锐 錯错 錫锡 鑼锣 錘锤 錦锦 鍵键 鋸锯 鍍镀 鎮镇 鎬镐 鏡镜 閉闭 闖闯 閒闲 悶闷
閘闸 聞闻 閥阀 閱阅 隊队 陣阵 階阶 陸陆 陳陈 陝陕 險险 隨随 隱隐 難难 雛雏 黴霉 霧雾 頁页 頂顶 項项
順顺 須须 頑顽 顧顾 頓顿 頒颁 預预 顱颅 領领 頰颊 頸颈 頻频 顆颗 題题 顏颜 額额 顛颠 顫颤 飄飘 飛飞
飢饥 飯饭 飲饮 飾饰 飽饱 飼饲 饒饶 館馆 饋馈 饞馋 饅馒 馭驭 馳驰 驅驱 駁驳 驢驴 駛驶 駐驻 駝驼 駕驾
罵骂 驕骄 駱骆 駭骇 驗验 駿骏 騎骑 騙骗 騷骚 驟骤 髏髅 魯鲁 鮮鲜 鯉鲤 鯨鲸 鱷鳄 鳩鸠 雞鸡 鳴鸣 鴉鸦
鷗鸥 鴿鸽 齒齿 齡龄 龔龚 兇凶 綺绮 綻绽 綽绰 頹颓 飆飙 餓饿 鬍胡 龜龟 靦腼 乾干 幹干
"""

_T2S_CACHE = None


def _load_t2s() -> dict:
    """繁体 -> 简体映射：外部 t2s.tsv 优先，其次内置高频字表"""
    global _T2S_CACHE
    if _T2S_CACHE is not None:
        return _T2S_CACHE
    table = {}
    try:
        with open(T2S_TABLE_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and len(parts[0]) == len(parts[1]):
                    for a, b in zip(parts[0], parts[1]):
                        table[a] = b
    except OSError:
        pass
    for tok in T2S_PARTIAL.split():
        if len(tok) == 2:
            table.setdefault(tok[0], tok[1])
    _T2S_CACHE = table
    return table


def to_simplified(text: str, table: dict = None) -> str:
    """繁体 -> 简体（只覆盖表内字符，未收录的原样保留）"""
    if not text:
        return text
    t = table if table is not None else _load_t2s()
    return "".join(t.get(c, c) for c in text)


def _match_candidates(cands, title_c, artist_c=""):
    """搜索结果排序：歌名+歌手都匹配 > 仅歌名匹配 > 其余，最多尝试 3 个"""
    cands = cands or []
    norm_t, norm_a = norm_text(title_c), norm_text(artist_c)

    def rank(it):
        name_ok = norm_text(it.get("name")) == norm_t
        singer_ok = bool(norm_a) and norm_a in norm_text(it.get("singer") or "")
        return (name_ok and singer_ok, name_ok)

    return sorted(cands, key=rank, reverse=True)[:3]


# ======================================================================
# 多源并行抓取：把「顺序轮询」改成「同时竞速」
# ======================================================================
# 旧实现按 QQ -> 网易云 -> 酷狗 -> LRCLIB 一个个试，耗时是各源之和；实测 LRCLIB
# 最坏要 12s+（国内网络访问 lrclib.net 不稳），用户点开一首歌要干等十几秒。
# 现在四个源同时开跑，谁先到、分高就用谁：正常歌曲 ≈ 第一个满配源返回的时间
# （实测 250~400ms），最坏也不超过单源上限。
_FETCH_TIMEOUT = {"qq": 4.0, "netease": 4.0, "kugou": 4.0, "lrclib": 3.0}
_FETCH_DOMESTIC_BUDGET = 1.8   # 等国内三源的硬上限（实测它们都 <400ms 到齐）
_FETCH_BUDGET = 4.0            # 整条链路总预算，含 LRCLIB 兜底
_FETCH_FULLMATCH_GRACE = 0.3   # 拿到满配后再多宽限 0.3s：稍慢但更优的同级源还有机会翻盘


def _fetch_source(src: str, query: str, title_c: str, artist_c: str):
    """单个来源的候选抓取（在并行线程里跑）；失败 / 无结果返回 None"""
    to = _FETCH_TIMEOUT.get(src, 6.0)
    cand = None
    if src == "qq":
        for it in _match_candidates(fetch_qq_search(query, timeout=to), title_c, artist_c):
            lyr, tr = fetch_qq_lyric(it["mid"], timeout=to) if it["mid"] else (None, "")
            pl, pw = parse_lrc(lyr) if lyr else ([], {})
            if pl:
                cover = None
                if it["albummid"]:
                    cover = ("https://y.gtimg.cn/music/photo_new/"
                             "T002R500x500M000%s.jpg" % it["albummid"])
                cand = {"lines": pl, "words": pw,
                        "trans": parse_trans(tr) if tr else [], "cover": cover}
                break
    elif src == "kugou":
        # 酷狗 KRC 自带逐字时间轴（借鉴 Lyricify 的酷狗源）
        for it in _match_candidates(fetch_kugou_search(query, timeout=to), title_c, artist_c):
            pl, pw, pt = fetch_kugou_lyric(it["name"], it["duration"], it["hash"], timeout=to)
            if pl:
                cand = {"lines": pl, "words": pw, "trans": pt, "cover": None}
                break
    elif src == "netease":
        for it in _match_candidates(fetch_netease_search(query, timeout=to), title_c, artist_c):
            pl, pw, pt = (fetch_netease_lyric_full(it["id"], timeout=to) if it["id"]
                          else ([], {}, []))
            if pl:
                cand = {"lines": pl, "words": pw, "trans": pt,
                        "cover": it["pic_url"] or None}
                break
    else:                                   # lrclib：候选里挑质量分最高的一个
        best = None
        for c in fetch_lrclib_candidates(title_c, artist_c, timeout=to):
            if best is None or (score_lyrics(c["lines"], c["words"], c["trans"], c["duration"])
                                > score_lyrics(best["lines"], best["words"], best["trans"],
                                               best["duration"])):
                best = c
        if best is not None:
            cand = {"lines": best["lines"], "words": best["words"], "trans": best["trans"],
                    "cover": None, "duration": best["duration"]}
    return cand


def _gather_sources(query, title_c, artist_c, duration, prefer_netease):
    """并行询问所有来源，边到边择优，返回 (lines, words, trans, cover, used_src, by_src)

    - 谁先到不一定用谁：按 score_lyrics 打分择优，同分时按来源优先级（QQ 优先 /
      正在用网易云播放则网易云优先）。
    - 拿到「逐字 + 翻译」满配后只再宽限 _FETCH_FULLMATCH_GRACE 秒：既不像旧版那样
      傻等最慢的源，也不至于因为「谁先到」就丢掉稍慢但更优的同级结果。
    - LRCLIB 很慢，只在「没结果或缺逐字」时才等它，且卡死在 _FETCH_BUDGET 内。
    """
    import queue as _queue

    order = ("netease", "qq", "kugou") if prefer_netease else ("qq", "netease", "kugou")
    srcs = order + ("lrclib",)
    rank = dict((s, i) for i, s in enumerate(order))
    rank["lrclib"] = len(order)
    t0 = time.time()
    q = _queue.Queue()

    def worker(src):
        try:
            cand = _fetch_source(src, query, title_c, artist_c)
        except Exception:
            log(src + " lyric failed: " + traceback.format_exc())
            cand = None
        q.put((src, cand))

    for s in srcs:
        threading.Thread(target=worker, args=(s,), daemon=True).start()

    by_src = {}
    lines, words, trans, cover = [], {}, [], None
    best_key, used_src = None, None

    def take(src, cand):
        """按质量分择优；返回是否已拿到「逐字 + 翻译」满配

        同分时的备用比较（score_lyrics 对行数的加分封顶在 25，超过就分不出高下）：
        逐字覆盖的行数多 > 翻译条数多 > 正文行数多 > 来源优先级靠前。
        不这么排的话，一个「35 行但逐字齐全」的结果会被「45 行、逐字更全」的挤掉。
        """
        nonlocal lines, words, trans, cover, best_key, used_src
        if not cand or not cand.get("lines"):
            return False
        sc = score_lyrics(cand["lines"], cand["words"], cand["trans"],
                          cand.get("duration") or duration)
        key = (sc, len(cand["words"] or {}), len(cand["trans"] or []),
               len(cand["lines"]), -rank.get(src, len(order) + 1))
        if best_key is None or key > best_key:
            best_key, used_src = key, src
            lines, words, trans = cand["lines"], cand["words"], cand["trans"]
            cover = cand.get("cover") or cover
        return bool(words and trans)

    try:
        # 第一轮：等国内三源。三源同时跑，正常 <700ms 到齐；_FETCH_DOMESTIC_BUDGET 只是防挂死。
        # 中途若已拿到「逐字 + 翻译」满配，就只再宽限一小会等更好的同级结果，然后收工。
        deadline = t0 + _FETCH_DOMESTIC_BUDGET
        grace_until = 0.0
        domestic_got = 0
        while domestic_got < len(order):
            stop_at = min(deadline, grace_until) if grace_until else deadline
            left = stop_at - time.time()
            if left <= 0:
                if not grace_until:
                    log("fetch: domestic budget exhausted (%d/%d arrived)"
                        % (domestic_got, len(order)))
                break
            try:
                src, cand = q.get(timeout=left)
            except _queue.Empty:
                break
            by_src[src] = cand
            # 只数国内源：LRCLIB 有时回得比国内源还快，若把它也计进配额，
            # 就会提前停止等待某个国内源（实测会把更优结果漏掉）。
            if src in order:
                domestic_got += 1
            if take(src, cand) and not grace_until:
                grace_until = time.time() + _FETCH_FULLMATCH_GRACE

        # 第二轮：没结果 / 缺逐字时，才等 LRCLIB 兜底（硬上限，绝不拖长）
        if (not lines or not words) and "lrclib" not in by_src:
            left = (t0 + _FETCH_BUDGET) - time.time()
            if left > 0:
                try:
                    src, cand = q.get(timeout=left)
                    by_src[src] = cand
                    # 已有正文时，只接受能补上逐字的 LRCLIB 候选
                    if cand and cand.get("lines") and (not lines or cand.get("words")):
                        take(src, cand)
                except _queue.Empty:
                    pass
    except Exception:
        log("parallel fetch failed: " + traceback.format_exc())
    return lines, words, trans, cover, used_src, by_src


def fetch_lyrics(title: str, artist: str, prefer_netease: bool = False, duration: float = 0.0):
    """带缓存的歌词抓取，返回 (lines, words, cover_url, trans)

    lines=[[t, 文本]...]；words={行号: [[t, dur, 词块]...]}（逐字数据存在时）
    trans=[[t, 翻译/音译]...]（QQ trans / 网易云 tlyric / 酷狗 KRC [language:]）
    来源：QQ音乐 / 网易云 / 酷狗（正在用网易云播放时优先）+ LRCLIB 兜底

    借鉴 Lyricify 的智能匹配引擎：每个源都先算质量分再择优（有逐字 > 有翻译 > 行数多），
    四个源并行竞速，拿到「逐字 + 翻译」的满配结果立即收工。
    """
    title_c, artist_c = clean_query_text(title), clean_query_text(artist)
    key = ("%s|%s" % (title_c, artist_c)).lower().strip()
    cp = _cache_path(key)
    if os.path.exists(cp):
        try:
            with open(cp, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("v") == 4:
                w = data.get("words") or {}
                cl, cw, ct = clean_lyrics(data.get("lines") or [],
                                          {int(k): v for k, v in w.items()},
                                          data.get("trans") or [])
                return cl, cw, data.get("cover") or None, ct
            if isinstance(data, dict):
                cl, cw, ct = clean_lyrics(data.get("lines") or [], {}, [])
                return cl, cw, data.get("cover") or None, ct
            if isinstance(data, list):
                cl, cw, ct = clean_lyrics(data, {}, [])
                return cl, cw, None, ct
        except Exception:
            pass
    query = "%s %s" % (title_c, artist_c) if artist_c else title_c
    lines, words, trans, cover_url, used_src, by_src = _gather_sources(
        query, title_c, artist_c, duration, prefer_netease)
    if lines and (not words or not trans) and used_src != "netease":
        # 缺逐字 / 翻译时借网易云同版本时间轴（同一录音版本一致）；
        # 网易云已经在并行结果里了，这里只是取用，不发新请求。
        nc = by_src.get("netease")
        if nc and nc.get("lines") and (nc.get("words") or nc.get("trans")):
            if nc.get("words") and not words:
                lines, words = nc["lines"], nc["words"]
            if nc.get("trans") and not trans:
                trans = nc["trans"]
            if not cover_url and nc.get("cover"):
                cover_url = nc["cover"]
    if lines:
        lines, words, trans = clean_lyrics(lines, words, trans)
    if lines:
        try:
            with open(cp, "w", encoding="utf-8") as f:
                json.dump({"v": 4, "cover": cover_url, "lines": lines, "trans": trans,
                           "words": {str(k): v for k, v in words.items()}},
                          f, ensure_ascii=False)
        except OSError:
            pass
    return lines, words, cover_url, trans


# ======================================================================
# 封面取色
# ======================================================================

DEFAULT_ACCENT1 = QColor("#7dd3fc")
DEFAULT_ACCENT2 = QColor("#c4b5fd")


def extract_accent(pix):
    """返回 (accent1, accent2)；无封面时用默认蓝紫"""
    try:
        if pix is None or pix.isNull():
            return QColor(DEFAULT_ACCENT1), QColor(DEFAULT_ACCENT2)
        img = pix.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).toImage()
        buckets = {}
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                h, s, v, _a = c.getHsvF()
                if h is None or v < 0.16 or s < 0.18:
                    continue
                buckets.setdefault((int(h * 12), int(s * 3), int(v * 3)), []).append((s, v, c))
        if not buckets:
            return QColor(DEFAULT_ACCENT1), QColor(DEFAULT_ACCENT2)
        scored = sorted(buckets.items(),
                        key=lambda kv: len(kv[1]) * (sum(s for s, _v, _c in kv[1]) / len(kv[1])),
                        reverse=True)

        def vivid(entry):
            cols = sorted(entry[1], key=lambda sv: sv[0] * 0.7 + sv[1] * 0.3, reverse=True)
            return QColor(cols[0][2])

        c1 = vivid(scored[0])
        best, best_d = None, -1.0
        h1 = c1.hueF()
        for entry in scored[1:6]:
            c = vivid(entry)
            d = abs(c.hueF() - h1)
            d = min(d, 1.0 - d)
            if d > best_d:
                best, best_d = c, d
        if best is None:
            best = QColor.fromHsvF((h1 + 0.08) % 1.0, c1.saturationF(), c1.valueF())
        out = []
        for c in (c1, best):
            h, s, v, _a = c.getHsvF()
            s = min(0.9, max(0.45, s))
            out.append(QColor.fromHsvF(h, s, 0.92))
        return out[0], out[1]
    except Exception:
        return QColor(DEFAULT_ACCENT1), QColor(DEFAULT_ACCENT2)


def pill_bg_color(accent: QColor) -> QColor:
    h, s, v, _a = accent.getHsvF()
    if h is None:
        h, s, v = 0.6, 0.3, 0.2
    return QColor.fromHsvF(h, min(0.6, s * 0.7), 0.16, 0.80)


# ======================================================================
# 媒体监听
# ======================================================================

def _to_seconds(v) -> float:
    if hasattr(v, "total_seconds"):
        return v.total_seconds()
    return float(v) / 10_000_000.0


def _live_pos(raw_pos: float, last_updated, status: str, now: float = None) -> float:
    """SMTC position 直传给下游，由 _apply_tick 的锚点外推负责平滑。

    ⚠️ 曾经这里按 Windows 媒体浮层算法做 `position + (now - last_updated_time)`
    外推，但实测 QQ音乐/网易云的 `position` 经常已经是最新值、而 `last_updated_time`
    却陈旧——再叠加一次陈旧度会**重复计数**，导致歌词整体跑快、与播放不同步
    （连默认主题都被带歪）。所以这里**不再自行外推**，直接返回播放器给的 position。

    平滑 + 防回拽 + 冻结免疫全部交给下游 `_apply_tick` 的锚点外推
    （anchor_pos + (monotonic - anchor_ts)，配合 _frozen_report 免疫）：
    它对「每 tick 都刷新的新鲜 position」和「几十秒不刷新的冻结快照」都处理正确，
    且不会双重计数。status 参数保留以便将来需要按状态分支时扩展。
    """
    return raw_pos


class MediaWatcher(QObject):
    mediaChanged = Signal(object)          # dict|None
    ticked = Signal(float, float, str)     # (position秒, duration秒, 状态)

    def __init__(self):
        super().__init__()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._key = None
        self._had_session = False
        self._last_source = ""
        self._session_id = ""          # 当前挂接的会话 AUMID，用于检测幽灵会话切换
        self._sess_log_t = 0.0         # 会话健康日志节流
        self._last_status = ""

    def start(self):
        self._thread.start()

    def activate(self):
        self._ready.set()

    def _run(self):
        try:
            asyncio.run(self._main())
        except Exception:
            log("watcher died:\n" + traceback.format_exc())

    @staticmethod
    def _lut_age(props) -> float:
        """last_updated_time 距现在的秒数；异常返回 -1（视为脏数据）"""
        try:
            lut = props.last_updated_time
            ts = (lut.timestamp() if hasattr(lut, "timestamp")
                  else float(lut) / 10_000_000.0 - 11644473600.0)
            if not ts:
                return -1.0
            return time.time() - ts
        except Exception:
            return -1.0

    @staticmethod
    def _pick_session(manager, last_source: str = ""):
        """选「活跃」会话，而非简单取第一个——规避幽灵会话（崩溃残留/重复启动）。

        优先级：正在播放 > 音乐类 App > 与上次同源（sticky）> 时间线更"新鲜"
        （last_updated_time 更近 = age 更小）。QQ音乐异常退出后 Windows 可能残留
        旧会话且永远不再更新，它的 position/status 都是死值；按新鲜度就能避开它。
        """
        sessions = list(manager.get_sessions())
        if not sessions:
            return None

        def score(s):
            try:
                st = str(s.get_playback_info().playback_status)
                playing = "PLAYING" in st
                src = (s.source_app_user_model_id or "").lower()
                music_app = any(k in src for k in ("qq", "cloudmusic", "spotify",
                                                   "wmplayer", "zune", "foobar"))
                sticky = bool(last_source) and src == last_source
                age = MediaWatcher._lut_age(s.get_timeline_properties())
                # age 越小越新鲜；age<0 视为脏，压到最低
                fresh = -age if age >= 0 else -1e9
                return (playing, music_app, sticky, fresh)
            except Exception:
                return (False, False, False, -1e9)

        sessions.sort(key=score, reverse=True)
        return sessions[0]

    async def _cover_bytes(self, props):
        try:
            thumb = props.thumbnail
            if thumb is None:
                return None
            stream = await thumb.open_read_async()
            size = int(stream.size)
            reader = DataReader(stream)
            await reader.load_async(size)
            buf = bytearray(size)
            reader.read_bytes(buf)  # winsdk: 传入数组就地填充
            return bytes(buf)
        except Exception:
            log("cover read failed:\n" + traceback.format_exc())
            return None

    async def _main(self):
        while not self._ready.is_set():
            await asyncio.sleep(0.05)
        # 延迟导入 SMTC 绑定：这 ~155ms 花在采集线程里，主线程不用等（启动更快）
        if not _load_smtc():
            return
        manager = await MediaManager.request_async()
        while True:
            try:
                session = self._pick_session(manager, self._last_source)
                if session is None:
                    if self._had_session:
                        self._had_session = False
                        self._key = None
                        self._last_source = ""
                        self._session_id = ""
                        self.mediaChanged.emit(None)
                    self.ticked.emit(0.0, 0.0, "CLOSED")
                    await asyncio.sleep(1.0)
                    continue
                self._had_session = True
                sid = session.source_app_user_model_id or ""
                # 会话切换（幽灵/重复启动）：强制复位歌词数据 + 重新锚定外推基准
                if sid != self._session_id:
                    n = len(list(manager.get_sessions()))
                    log("SMTC 会话切换: %r -> %r（当前共 %d 个会话），复位歌词与基准"
                        % (self._session_id or "<none>", sid, n))
                    self._session_id = sid
                    self._last_source = sid
                    self._key = None
                    self.mediaChanged.emit(None)
                self._last_source = sid
                tl = session.get_timeline_properties()
                props = await session.try_get_media_properties_async()
                title = props.title or ""
                artist = props.artist or ""
                key = (title, artist)
                if key != self._key:
                    self._key = key
                    cover = await self._cover_bytes(props)
                    self.mediaChanged.emit({
                        "title": title,
                        "artist": artist,
                        "album": props.album_title or "",
                        "source": sid,
                        "cover": cover,
                        # 歌曲总时长：歌词多源择优时用来判断"末行是否贴合全长"
                        "duration": max(0.0, _to_seconds(tl.end_time)),
                    })
                status = str(session.get_playback_info().playback_status).split(".")[-1]
                raw_pos = _to_seconds(tl.position)
                age = self._lut_age(tl)
                dur = _to_seconds(tl.end_time)
                # position 是 last_updated_time 时刻的快照，PLAYING 时按陈旧度外推成实时值
                pos = _live_pos(raw_pos, tl.last_updated_time, status)
                self.ticked.emit(pos, dur if dur > 0 else 0.0, status)
                # 会话健康快照（~20s 一次）：用于事后区分"真 Paused" / "幽灵死会话"
                now = time.time()
                if status != self._last_status or now - self._sess_log_t > 20.0:
                    self._last_status = status
                    self._sess_log_t = now
                    if status != "PLAYING":
                        log("会话健康: AUMID=%s status=%s raw_pos=%.1f age=%.1fs "
                            "→ 外推值=%.1f（非 PLAYING，冻结属于系统正确行为）"
                            % (sid, status, raw_pos, max(age, 0.0), pos))
                    else:
                        log("会话健康: AUMID=%s status=PLAYING raw_pos=%.1f age=%.1fs "
                            "→ 外推值=%.1f" % (sid, raw_pos, max(age, 0.0), pos))
                await asyncio.sleep(0.5)
            except Exception:
                log("poll error:\n" + traceback.format_exc())
                await asyncio.sleep(1.5)


# ======================================================================
# 悬浮窗
# ======================================================================

MARGIN = 28          # 玻璃样式四周留白（给投影留空间）
PILL_RADIUS = 18
PAD_L, PAD_R, GAP, COVER = 16, 20, 14, 72
H_NORMAL, H_WAITING = 100, 78
MARGIN_N, COVER_N, GAP_N = 12, 54, 13   # 原生浮字样式
# iOS 音乐卡片
MARGIN_IOS, IOS_COVER, IOS_GAP, IOS_RADIUS = 20, 84, 16, 24
# Spotify 声波卡片
MARGIN_SP, SP_PAD_L, SP_PAD_R, SP_GAP, SP_COVER, SP_RADIUS = 22, 16, 18, 14, 64, 14
SPOTIFY_GREEN = QColor("#1DB954")
# 黑胶唱片
VINYL_DISC, VINYL_GAP, MARGIN_V = 104, 18, 16

# ---- 文字描边强度（v2.4.16 柔和化）----
#
# 分「有卡片底」和「无卡片底」两档，理由是两者面对的背景完全不同：
#   无卡片（原生浮字 / 黑胶）：文字直接压在壁纸上，必须靠落影保证可读性，
#     否则遇到复杂壁纸就糊成一片 → HALO_BARE。
#   有卡片：卡片本身已经和桌面分离了，文字只需要极淡的托起感 →
#       · 玻璃：底色是**半透明**的（alpha 198~226），壁纸会透上来，所以给 HALO_CARD；
#       · iOS / Spotify：底色接近不透明（alpha 214~240），压根不需要描边，
#         维持 halo_on=False（iOS 一直如此，也是五套里最耐看的一套）。
# 数值是传给 _halo_pens 的基准宽度；实际可见外延约为它的一半（居中描边被 fill 盖掉内半边）。
HALO_CARD = 2.4
HALO_BARE = 3.4
# 未唱到的字的不透明度：无卡片样式要给足，否则在浅色壁纸上根本读不出来。
DIM_CARD, DIM_BARE = 108, 150

# ---- UI 质感令牌（v2.4.18）----------------------------------------------------
# 深色界面上一块平板要读成"有厚度的面"，靠的是三件事：
#   ① 顶部一条受光带（光从上方来）—— 用渐变头 4% 提亮实现，比加投影便宜；
#   ② 分层描边：上亮、下暗 —— 上边缘"接光"、下边缘"落影"，一下就立起来了；
#   ③ 交互态反转受光方向 —— 按下时顶部变暗、内部压深，读成"被按进去"。
# 这几个数值以前散落在各条 QSS 里各写各的，视觉语言不统一；现在集中到一处，
# 面板 / 控件 / 菜单 / 浮层共用同一套"光从上方来"的假设。
UI_R_CARD = 14                 # 卡片圆角
UI_R_CTRL = 9                  # 按钮 / 下拉圆角
UI_R_ICONBTN = 11              # 图标按钮（头部控制键）圆角
UI_CARD_TOP = "#242935"        # 卡片顶部受光带
UI_CARD_BODY = "#1b1f28"       # 卡片主体
UI_CARD_BOT = "#13161c"        # 卡片底部（略暗 = 落影）
UI_CTRL_TOP = "#272c38"        # 按钮渐变顶色
UI_CTRL_BOT = "#1b1f27"        # 按钮渐变底色
UI_EDGE_HI = "rgba(255,255,255,36)"     # 上边缘描边（接光）
UI_EDGE_LO = "rgba(0,0,0,80)"           # 下边缘描边（落影）
UI_EDGE_MID = "rgba(255,255,255,20)"    # 左右描边（中性）
UI_GROOVE = "#080a0e"          # 凹槽（滑块轨道 / 分段轨道）打底色

# 逐字卡拉OK的「柔性波前」（v2.4.18）：正在唱的那个字沿字宽铺横向渐变，
# 让"唱过/未唱"的边界是渐隐而不是硬切。关掉即回到"整字平色"的旧观感——
# 留这个开关是为了 A/B 对照（预览脚本靠它出对照图）。
KARAOKE_SOFT_EDGE = True

STYLE_NAMES = {
    "native": "原生浮字",
    "glass": "玻璃胶囊",
    "ios": "iOS 音乐卡片",
    "vinyl": "黑胶唱片",
    "spotify": "Spotify 声波",
}

# 主题投影特效总开关（v2.4.13）：所有悬浮主题统一用「原生浮字」那套逻辑——不挂投影。
#
# 背景：QGraphicsDropShadowEffect 会在**每帧**把整个窗口渲染到离屏图、再做多趟高斯
# 模糊后合成。原生浮字从 v2.4 起就关掉了它（就地注释：省掉每帧的全窗口模糊重绘），
# 也是唯一一个逐字动画始终跟手、不卡的样式；其余四个主题都开着 16~26px 模糊，
# 在「无边框 + WA_TranslucentBackground」的窗口上每帧都要额外走一遍模糊 + DWM 合成，
# 逐字动画就会被拖住。
#
# 现在四个卡片主题照抄原生的逻辑：卡片靠自身渐变底 + 1px 描边与桌面分离，不吃每帧模糊。
# 想恢复投影把这里改成 True 即可。
THEME_DROP_SHADOW = False

# 摆放位置预设（借鉴 FluentFlyout 的可定制浮层位置）。
# 存的是"相对屏幕安全区的锚点"而不是绝对坐标，换分辨率 / 改任务栏高度后仍然贴边。
POSITION_MARGIN = 84          # 距屏幕边缘留白（与默认"贴任务栏上方"一致）
POS_FREE = "free"             # 用户手动拖过 = 自由位置，不再套预设
POSITION_PRESETS = (
    ("bottom", "底部居中（贴任务栏上方）"),
    ("top", "顶部居中"),
    ("center", "屏幕正中"),
    ("top_left", "左上角"),
    ("top_right", "右上角"),
    ("bottom_left", "左下角"),
    ("bottom_right", "右下角"),
)
POSITION_PRESET_NAMES = dict(POSITION_PRESETS)

# 切行动画：key -> 显示名（面板 / 校验的唯一真源）
ANIM_STYLES = {
    "slide": "流光滑入",
    "rise": "字字上浮",
    "zoom": "缩放入场",
    "fade": "纯淡入",
    "pop": "弹跳落字",
    "wave": "波浪起伏",
    "fan": "扇形展开",
    "typer": "打字机",
    "none": "无动画",
}

# 中文星期（strftime 的 %A 跟随 C locale 会输出英文，屏保里用这个）
WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# 逐字动画参数
FAN_R_FACTOR = 2.6      # 扇形半径 = 行宽 × 该系数（越大越平缓）
FAN_R_MIN = 380.0       # 扇形半径下限（短句也保留弧度）
WAVE_AMP = 0.11         # 波浪振幅，相对字号

APP_VERSION = "1.0.0"

# ---------------- 内置更新源 ----------------
# 分工：GitHub Releases API 负责回答「有没有新版本、版本号是多少」，
# 真正下载默认走蓝奏云镜像（国内直连更快）。两者都内置，用户不用手填地址。
UPDATE_REPO = "xiaohao8/Desktop-sing"        # GitHub（源码主仓）
GITEE_REPO = "xiaohao3/Desktop-sing"         # Gitee（国内镜像仓，API/raw 文件都能直连）
DEFAULT_UPDATE_URL = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
GITHUB_RELEASES_PAGE = "https://github.com/%s/releases" % UPDATE_REPO
GITEE_RELEASES_PAGE = "https://gitee.com/%s/releases" % GITEE_REPO
GITEE_RELEASES_API = "https://gitee.com/api/v5/repos/%s/releases/latest" % GITEE_REPO

# 备用更新源：主源（GitHub API）拉不动时按顺序尝试，取版本号最高的那个有效结果。
# 顺序有讲究——国内直连的 Gitee 排前面，海外 CDN 兜底。
#   ① Gitee Releases API：Gitee 发过 release 时可用（现阶段还没发，会自动跳过）
#   ② Gitee raw 的 update.json：国内直连最快，含蓝奏云链接
#   ③ jsDelivr 反代 GitHub 仓库的 update.json：海外 / Gitee 都不可达时兜底
UPDATE_FALLBACK_SOURCES = [
    GITEE_RELEASES_API,
    "https://gitee.com/%s/raw/main/update.json" % GITEE_REPO,
    "https://cdn.jsdelivr.net/gh/%s@main/update.json" % UPDATE_REPO,
]

# 蓝奏云镜像表：版本号 → {"setup": 安装版, "portable": 免安装版}。
# 发新版时把新的蓝奏云分享链接补进这里即可；
# 表里查不到该版本时，会自动退回 GitHub 资源直链，保证任何情况下都有得下。
LANZOU_MIRRORS = {
    "1.0.0": {
        "setup": "https://wwbgk.lanzouu.com/iTgxJ48z9kjg",
        "portable": "https://wwbgk.lanzouu.com/ih2SA48z8rmf",
    },
}


def lanzou_mirror(ver: str) -> dict:
    """取某版本的蓝奏云镜像；未收录返回空字典（调用方据此回落 GitHub 直链）。"""
    m = LANZOU_MIRRORS.get(str(ver or "").strip().lstrip("vV"))
    return m if isinstance(m, dict) else {}


# 精选适合听歌场景的字体（按本机安装情况过滤；覆盖中英文）
CURATED_FONTS = [
    "MiSans", "MiSans Semibold", "HarmonyOS Sans SC", "OPPO Sans",
    "Alibaba PuHuiTi 3.0", "Alibaba PuHuiTi", "Source Han Sans CN",
    "Noto Sans SC", "PingFang SC", "Microsoft YaHei UI",
    "Segoe UI", "Poppins", "Montserrat", "Nunito",
]

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                # 走守护进程启动，开机后崩溃也能自动拉回
                parts = _app_command(supervise=bool(load_config().get("keepalive", True)))
                cmd = " ".join(('"%s"' % p) if " " in p else p for p in parts)
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        log("autostart failed:\n" + traceback.format_exc())
        return False


# ======================================================================
# 进程保活：守护进程（--supervise）+ 心跳哨兵
#   Windows 上线程救不了「进程整个挂掉」，所以保活必须有一个外部监工：
#   监工只做一件事 —— 拉起主程序、盯着它，非正常退出就退避后重拉。
#   用户点「退出」是正常退出（exit 0），监工随之收工，不会诈尸。
# ======================================================================
SUPERVISE_FLAG = "--supervise"
WATCH_PID_FLAG = "--watch-pid"
SELFTEST_FLAG = "--selftest"
SUPERVISED_ENV = "DESKTOP_LYRICS_SUPERVISED"
SUPERVISOR_PID = os.path.join(CFG_DIR, "supervisor.pid")
STOP_SENTINEL = os.path.join(CFG_DIR, "keepalive.off")   # 存在 = 不要保活
RESTART_SIG = os.path.join(CFG_DIR, "restart.sig")       # 新版接管请求：旧实例见之即退


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259      # STILL_ACTIVE
    except Exception:
        return False


def supervisor_alive() -> bool:
    try:
        with open(SUPERVISOR_PID, encoding="utf-8") as f:
            return _pid_alive(int(f.read().strip()))
    except Exception:
        return False


def _app_command(supervise: bool = False, watch_pid: int = 0) -> list:
    """当前程序的重启命令行（兼容源码运行 / 打包 exe）"""
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = pyw if os.path.exists(pyw) else sys.executable
        cmd = [exe, os.path.abspath(__file__)]
    if supervise:
        cmd.append(SUPERVISE_FLAG)
        if watch_pid:
            cmd += [WATCH_PID_FLAG, str(int(watch_pid))]
    return cmd


def spawn_supervisor():
    """拉起守护进程来监护「当前这个进程」

    关键点：守护进程不会另起一个主程序（那会被单实例守卫挡下），而是先把自己挂到
    当前 PID 上 —— 当前进程一挂，它才开始接管拉起。所以「保活」对运行中的实例同样有效。
    """
    if os.environ.get(SUPERVISED_ENV):
        return
    if supervisor_alive():
        # 升级接管场景：旧守护进程正带着停机哨兵退出，等它退完再拉自己的，
        # 否则新实例跳过拉起、旧守护进程随后收工，新实例就失去保活了
        if os.path.exists(STOP_SENTINEL):
            deadline = time.time() + 6.0
            while time.time() < deadline and supervisor_alive():
                time.sleep(0.25)
            if supervisor_alive():
                log("旧守护进程未退出，本次不重复拉起")
                return
        else:
            return
    try:
        if os.path.exists(STOP_SENTINEL):
            os.remove(STOP_SENTINEL)
    except OSError:
        pass
    import subprocess
    cmd = _app_command(supervise=True, watch_pid=os.getpid())
    flags = 0x00000008 | 0x08000000   # DETACHED_PROCESS | CREATE_NO_WINDOW
    try:
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
        log("已拉起保活守护进程（监护 pid=%d）" % os.getpid())
    except Exception:
        log("拉起守护进程失败:\n" + traceback.format_exc())


def stop_supervisor():
    """写停机哨兵；守护进程下一轮巡检即自行退出"""
    try:
        with open(STOP_SENTINEL, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass


def run_supervisor(watch_pid: int = 0):
    """守护进程主循环

    watch_pid > 0：先盯着这个已有进程（保活运行中的实例），它退出后再进入拉起循环。
    watch_pid = 0：直接进入拉起循环（开机自启场景，由守护进程负责把主程序带起来）。
    """
    import subprocess
    try:
        with open(SUPERVISOR_PID, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    try:
        if os.path.exists(STOP_SENTINEL):
            os.remove(STOP_SENTINEL)
    except OSError:
        pass
    env = dict(os.environ)
    env[SUPERVISED_ENV] = "1"
    cmd = _app_command(supervise=False)
    backoff = 3
    restarts = 0
    log("守护进程启动 pid=%d watch=%d" % (os.getpid(), watch_pid))
    # 第一阶段：监护已运行的实例
    while watch_pid and _pid_alive(watch_pid):
        if os.path.exists(STOP_SENTINEL):
            log("收到停机哨兵（监护阶段），守护进程退出")
            _cleanup_pid_file()
            return 0
        time.sleep(1.5)
    if watch_pid:
        log("被监护进程 %d 已退出，转入接管模式" % watch_pid)
    while True:
        if os.path.exists(STOP_SENTINEL):
            log("收到停机哨兵，守护进程退出")
            break
        try:
            proc = subprocess.Popen(cmd, env=env, close_fds=True)
        except Exception:
            log("守护进程拉起主程序失败:\n" + traceback.format_exc())
            break
        code = proc.wait()
        if code == 0 or os.path.exists(STOP_SENTINEL):
            log("主程序正常退出，守护进程收工")
            break
        restarts += 1
        log("主程序异常退出（code=%s），%.0fs 后第 %d 次重启" % (code, backoff, restarts))
        time.sleep(backoff)
        backoff = min(60, backoff * 2)      # 退避，避免崩溃风暴
    _cleanup_pid_file()
    return 0


def _cleanup_pid_file():
    try:
        os.remove(SUPERVISOR_PID)
    except OSError:
        pass


# ======================================================================
# 空闲 / 锁屏检测：氛围屏保用
# ======================================================================

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """系统空闲秒数（无键鼠输入），失败返回 0"""
    try:
        li = _LASTINPUTINFO()
        li.cbSize = ctypes.sizeof(li)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
            return 0.0
        # dwTime 是 32 位毫秒计数，这里同样用 GetTickCount() 保证位宽一致；
        # 差值按 2^32 取模，跨越 49.7 天翻转也不会算成负数
        ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint32
        ticks = int(ctypes.windll.kernel32.GetTickCount())
        return max(0.0, ((ticks - int(li.dwTime)) & 0xFFFFFFFF) / 1000.0)
    except Exception:
        return 0.0


DESKTOP_READOBJECTS = 0x0001
DESKTOP_SWITCHDESKTOP = 0x0100


def session_locked() -> bool:
    """工作站是否已锁屏：锁屏后拿不到 input desktop"""
    try:
        h = ctypes.windll.user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
        if not h:
            return True
        ctypes.windll.user32.CloseDesktop(h)
        return False
    except Exception:
        return False


def make_app_icon() -> QIcon:
    """应用图标：优先用打包自带的 icon.png（品牌图），缺失时回退程序绘制。

    icon.png 与 icon.ico 同源：源码目录放一份（打包时 --add-data 进 exe），
    运行时从程序目录（onedir）或解包目录（onefile 的 sys._MEIPASS）找。
    """
    for base in (getattr(sys, "_MEIPASS", ""), APP_DIR):
        if not base:
            continue
        cand = os.path.join(base, "icon.png")
        if os.path.isfile(cand):
            ic = QIcon(cand)
            if not ic.isNull():
                return ic
    return _make_app_icon_drawn()


def _make_app_icon_drawn() -> QIcon:
    """回退：渐变圆角方块 + 音符"""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, 64, 64)
    grad.setColorAt(0, DEFAULT_ACCENT1)
    grad.setColorAt(1, DEFAULT_ACCENT2)
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 16, 16)
    p.setPen(QPen(QColor(20, 24, 32)))
    f = QFont("Segoe UI Symbol")
    f.setPixelSize(34)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "♪")
    p.end()
    return QIcon(pix)


def _round_tri(cx, cy, u: float, hw: float, direction: int) -> QPainterPath:
    """三角路径：u = 半高，hw = 半宽，direction=1 向右 / -1 向左

    尖角不手算贝塞尔 —— 调用方用「同色圆角描边 + fillPath」给它做视觉倒角，
    圆头描边天然把三个尖角磨圆，比逐点算圆弧简单且更均匀。
    """
    path = QPainterPath()
    dx = direction * hw
    path.moveTo(cx - dx, cy - u)
    path.lineTo(cx + dx, cy)
    path.lineTo(cx - dx, cy + u)
    path.closeSubpath()
    return path


def draw_media_glyph(p: QPainter, kind: str, r: QRectF, color: QColor):
    """矢量绘制媒体控制图标（圆角现代风）

    不依赖任何 emoji / 符号字体，避免在缺字型的机器上变成方框。
    prev/next 用「圆角三角 + 圆头竖条」的现代播放器语汇，play 用单圆角三角，
    pause 用两根圆头竖条，gear 用细描边齿轮（有内孔，不做「黑饼」）。
    """
    p.save()
    cx, cy = r.center().x(), r.center().y()
    u = r.height() * 0.28
    col = QColor(color)
    p.setPen(Qt.NoPen)
    p.setBrush(col)

    def filled(path):
        # 同色圆角描边 = 给三角形倒角，视觉更现代、不扎眼
        p.strokePath(path, QPen(col, u * 0.34, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.fillPath(path, col)

    if kind == "play":
        filled(_round_tri(cx - u * 0.12, cy, u * 0.94, u * 0.66, 1))
    elif kind == "pause":
        bw, gap = u * 0.46, u * 0.30
        for x in (cx - gap - bw, cx + gap):          # 两竖条左右对称
            p.drawRoundedRect(QRectF(x, cy - u, bw, 2 * u), bw / 2, bw / 2)
    elif kind == "prev":
        # 左端圆头竖条 + 向左三角（现代播放器语汇：跳到开头）
        p.drawRoundedRect(QRectF(cx - u * 0.82, cy - u * 0.82, u * 0.32, u * 1.64),
                          u * 0.16, u * 0.16)
        filled(_round_tri(cx + u * 0.07, cy, u * 0.74, u * 0.49, -1))
    elif kind == "next":
        p.drawRoundedRect(QRectF(cx + u * 0.50, cy - u * 0.82, u * 0.32, u * 1.64),
                          u * 0.16, u * 0.16)
        filled(_round_tri(cx - u * 0.07, cy, u * 0.74, u * 0.49, 1))
    elif kind == "gear":
        # 圆头齿 + 描边外环 + 挖孔：整体是「线面结合」的现代设置图标
        p.save()
        p.translate(cx, cy)
        for i in range(6):
            p.save()
            p.rotate(i * 60.0)
            p.drawRoundedRect(QRectF(-u * 0.17, -u * 1.30, u * 0.34, u * 0.50),
                              u * 0.17, u * 0.17)
            p.restore()
        p.setPen(QPen(col, max(1.0, u * 0.22)))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), u * 0.92, u * 0.92)
        p.setPen(QPen(col, max(1.0, u * 0.20)))
        p.drawEllipse(QPointF(0, 0), u * 0.34, u * 0.34)
        p.restore()
    elif kind == "saver":      # 氛围屏保：月亮 + 一点点星
        p.translate(cx, cy)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        moon = QPainterPath()
        moon.addEllipse(QPointF(-u * 0.10, 0), u * 0.92, u * 0.92)
        cut = QPainterPath()
        cut.addEllipse(QPointF(u * 0.30, -u * 0.16), u * 0.82, u * 0.82)
        p.fillPath(moon.subtracted(cut), col)
        for (sx, sy, sr) in ((u * 1.05, -u * 0.75, u * 0.13),
                             (u * 1.25, u * 0.22, u * 0.09)):
            p.drawEllipse(QPointF(sx, sy), sr, sr)
    elif kind == "refresh":    # 环形箭头：缺口圆环 + 端点小三角（重新获取 / 刷新）
        p.setPen(QPen(col, max(1.4, u * 0.26), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - u * 0.80, cy - u * 0.80, u * 1.60, u * 1.60),
                  70 * 16, 268 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        tri = QPainterPath()
        tri.moveTo(-u * 0.34, -u * 0.30)
        tri.lineTo(u * 0.34, 0.0)
        tri.lineTo(-u * 0.34, u * 0.30)
        tri.closeSubpath()
        p.save()
        p.translate(cx + u * 0.70, cy - u * 0.36)
        p.rotate(38)
        filled(tri)
        p.restore()
    elif kind == "quit":       # 电源符号：顶部留缺口的圆环 + 中间竖条
        p.setPen(QPen(col, max(1.4, u * 0.26), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - u * 0.84, cy - u * 0.84, u * 1.68, u * 1.68),
                  125 * 16, 290 * 16)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(cx - u * 0.15, cy - u * 1.14, u * 0.30, u * 1.20),
                          u * 0.15, u * 0.15)
    p.restore()


def menu_qss(accent: QColor) -> str:
    """托盘 / 右键菜单的现代深色皮肤（跟随封面主色）

    有几样必须显式写出来，缺一个就会退化：
      · **font-family** —— 菜单是顶层弹出窗口，**不会**继承设置面板的 QSS 字体。
        不写就落到 Qt 默认字体上，既不跟面板一致，也不跟用户选的字号走。
      · **子菜单箭头** —— 只给 `width` 不给 `image` 时 Qt 会退回系统原生小三角，
        跟下拉框那边的自制 chevron 对不上风格，所以统一换图。
      · **勾选标记** —— 「主色圆角块 + 白色对勾」两层叠，比纯色块更容易读出"已选中"。
      · **border-radius** —— 圆角需要弹出窗口是半透明的，QMenu 挂上样式表后 Qt 会处理。
    """
    a = accent.name()
    arrow = ui_icon_url("menu_arrow")
    check = ui_icon_url("menu_check")

    arrow_rule = ("QMenu::right-arrow { image: url(%s); width: 12px; height: 12px; }" % arrow) \
        if arrow else "QMenu::right-arrow { width: 12px; }"
    check_rule = ("QMenu::indicator:checked { background: __A__; border-radius: 4px;\n"
                  "                                  image: url(%s); }" % check) \
        if check else "QMenu::indicator:checked { background: __A__; border-radius: 4px; }"

    qss = """
    QMenu { background: #15181f; color: #dfe4ee;
            font-family: "Microsoft YaHei UI"; font-size: 13px;
            border: 1px solid rgba(255,255,255,26); border-radius: 10px;
            padding: 6px; }
    QMenu::item { padding: 7px 30px 7px 26px; border-radius: 7px; }
    QMenu::item:selected { background: __A__; color: #10131a; }
    QMenu::item:disabled { color: #6f7787; }
    QMenu::separator { height: 1px; background: rgba(255,255,255,22); margin: 6px 10px; }
    QMenu::indicator { width: 14px; height: 14px; margin-left: 7px; }
    __CHECK__
    __ARROW__
    """
    return (qss.replace("__CHECK__", check_rule)
               .replace("__ARROW__", arrow_rule)
               .replace("__A__", a))


def make_media_icon(kind: str, color: QColor = None, size: int = 18) -> QIcon:
    """把矢量图标包装成 QIcon（面板按钮用），同样不依赖字体"""
    ss = size * 2
    pm = QPixmap(ss, ss)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw_media_glyph(p, kind, QRectF(0, 0, ss, ss),
                     color or QColor(214, 220, 232))
    p.end()
    return QIcon(pm)


def make_menu_icon(kind: str, size: int = 16,
                   color: QColor = None, sel_color: QColor = None) -> QIcon:
    """菜单项图标：普通态浅灰、选中态深色（选中行是主色填充，浅灰图标会糊在一起）。

    Qt 的 QMenu 在行动态高亮时会切到 `QIcon::Selected` 模式取图，所以这里把两张
    不同颜色的位图分别挂到 Normal / Selected / Active 三种模式下——
    一个 QIcon 就能同时满足"未选中浅灰、选中深色"两种底。
    """
    col = color or QColor(198, 205, 219)
    sel = sel_color or QColor(16, 19, 26)
    ic = QIcon()
    for mode, c in ((QIcon.Normal, col), (QIcon.Active, col), (QIcon.Selected, sel)):
        ss = size * 2
        pm = QPixmap(ss, ss)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        draw_media_glyph(p, kind, QRectF(0, 0, ss, ss), c)
        p.end()
        ic.addPixmap(pm, mode, QIcon.Off)
    return ic


def make_play_icon(bg: QColor = None, glyph: str = "play",
                   color: QColor = None, size: int = 26) -> QIcon:
    """实心主色圆底 + 白色三角/双竖条的播放按钮图标（面板主按钮用）

    注意：颜色分工是「圆底 = bg 主色，图形 = color 白色」，
    不要图省事把主色传成图形色，否则会变成同色叠同色、什么都看不见。
    """
    ss = size * 2
    pm = QPixmap(ss, ss)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(bg or QColor(DEFAULT_ACCENT1))
    p.drawEllipse(QPointF(ss / 2, ss / 2), ss * 0.46, ss * 0.46)
    draw_media_glyph(p, glyph, QRectF(ss * 0.15, ss * 0.15, ss * 0.70, ss * 0.70),
                     color or QColor(255, 255, 255, 250))
    p.end()
    return QIcon(pm)


def _ui_glyph_url(name: str, draw) -> str:
    """把一张矢量小图画成 PNG 落到配置目录，返回可直接写进 QSS 的路径（正斜杠）。

    Qt 的 QSS **不支持**任何 CSS 图形写法（border 三角形那套写了不报错，但渲染成一个小
    方块），只认 `image: url(...)` 这种真实图片。所以所有 QSS 小图标都得先画成文件。
    文件已存在就直接复用，不重复写盘；写不出来返回 ""，调用方回退成不画图标。
    """
    path = os.path.join(CFG_DIR, name + ".png")
    if not os.path.exists(path):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            ss = 24
            pm = QPixmap(ss, ss)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            draw(p, ss)
            p.end()
            pm.save(path, "PNG")
        except OSError:
            return ""
    return path.replace("\\", "/")


def _draw_chevron(p: QPainter, ss: int, down: bool = True, color: str = "#9aa3b5"):
    """两笔连成一个 chevron（不引 QPolygonF，少一个依赖）"""
    pen = QPen(QColor(color), 2.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    if down:
        p.drawLine(QPointF(6.5, 9.5), QPointF(12.0, 15.0))
        p.drawLine(QPointF(12.0, 15.0), QPointF(17.5, 9.5))
    else:                                   # 指向右侧（子菜单箭头）
        p.drawLine(QPointF(9.5, 6.5), QPointF(15.0, 12.0))
        p.drawLine(QPointF(15.0, 12.0), QPointF(9.5, 17.5))


def _draw_check(p: QPainter, ss: int, color: str = "#ffffff"):
    """白色对勾——QSS 里叠在主色圆角块上，两层一起读出「已选中」"""
    pen = QPen(QColor(color), 3.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(QPointF(5.5, 12.6), QPointF(9.8, 17.0))
    p.drawLine(QPointF(9.8, 17.0), QPointF(18.5, 7.4))


def ui_icon_url(kind: str) -> str:
    """按用途取一张已落盘的 QSS 小图标

    kind: combo_arrow（下拉框箭头）/ menu_arrow（子菜单箭头）/ menu_check（勾选标记）
    """
    if kind == "combo_arrow":
        return _ui_glyph_url("chevron_down", lambda p, s: _draw_chevron(p, s, down=True))
    if kind == "menu_arrow":
        return _ui_glyph_url("chevron_right", lambda p, s: _draw_chevron(p, s, down=False))
    if kind == "menu_check":
        return _ui_glyph_url("check_white", _draw_check)
    return ""


def combo_arrow_url() -> str:
    """下拉箭头小图路径（薄封装，保留旧调用点）"""
    return ui_icon_url("combo_arrow")


def round_pixmap(pm: QPixmap, radius: float) -> QPixmap:
    """按圆角裁一张 pixmap。

    需要这个是因为：QLabel 上的 `border-radius` 只圆它自己的背景，**不会裁**作为
    内容画进去的 pixmap。屏保缩略图就是这样——底下是圆角、上面的 pixmap 四角仍是方的，
    看起来像"圆角框里塞了张方图"。圆角必须画在 pixmap 本身上。
    """
    out = QPixmap(pm.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pm.width(), pm.height()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def fix_combo_popup(combo: QComboBox):
    """修掉下拉弹层外面那圈白色边框。

    `QComboBox QAbstractItemView` 只能美化**内层列表视图**。弹层真正的窗口是 Qt 私有的
    `QComboBoxPrivateContainer`（QFrame 子类），它不在样式表的常规可选中范围内，会照默认
    调色板画出浅色底 + 灰边框——于是深色列表被套了一圈 1~4px 白边，圆角也白做了。

    实测三种写法：
      · 裸声明（`background: transparent; border: none;`）→ 白边没了，但会连带作用到
        内层视图，把背景色也改掉；
      · `.QFrame { ... }` → **匹配不到**（Qt 的 `.XXX` 只匹配精确类，不含子类）；
      · `QComboBoxPrivateContainer { ... }` → 只打容器，白边消失且内层保持原样。用这个。
    """
    try:
        view = combo.view()
        pop = view.window() if view is not None else None
        if pop is not None and pop is not combo:
            pop.setStyleSheet(
                "QComboBoxPrivateContainer { background: transparent; border: none; }")
    except Exception:
        pass


def build_message_box(parent, title: str, text: str, informative: str = "",
                      accent: QColor = None, warning: bool = False) -> QMessageBox:
    """构造（但不弹出）一个深色皮肤的 QMessageBox。

    与 `styled_message` 拆开是为了**可测/可截图**：`exec()` 会阻塞，测试没法驱动。

    用不着 `QMessageBox.about()` / `.warning()` —— 那些**静态方法**新起的是系统原生
    对话框，既不继承设置面板的样式表、也不继承菜单皮肤，整个应用就剩它们是白底。
    """
    a = (accent or QColor(DEFAULT_ACCENT1)).name()
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    if informative:
        box.setInformativeText(informative)
    box.setIcon(QMessageBox.Warning if warning else QMessageBox.Information)
    box.setStyleSheet("""
    QMessageBox { background: #15181f; }
    QMessageBox QLabel { color: #dfe4ee; font-family: "Microsoft YaHei UI"; font-size: 13px; }
    QMessageBox QLabel#qt_msgbox_informativelabel { color: #98a0b2; font-size: 12px; }
    QMessageBox QPushButton { background: #1e222b; color: #dfe4ee;
                              border: 1px solid rgba(255,255,255,24);
                              border-radius: 8px; padding: 6px 18px; min-width: 60px; }
    QMessageBox QPushButton:hover { border-color: __A__; color: #ffffff; }
    QMessageBox QPushButton:default { background: __A__; color: #10131a;
                                      border: none; font-weight: 700; }
    QMessageBox QPushButton:default:hover { background: #ffffff; }
    """.replace("__A__", a))
    return box


def styled_message(parent, title: str, text: str, informative: str = "",
                   accent: QColor = None, warning: bool = False):
    """深色皮肤的模态对话框（见 build_message_box）"""
    build_message_box(parent, title, text, informative, accent, warning).exec()


class UpdateDialog(QDialog):
    """发现新版本时的升级提示弹窗：展示版本与更新说明，并提供「前往下载」。"""

    def __init__(self, parent, info: dict):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        accent = QColor(getattr(parent, "accent1", QColor(DEFAULT_ACCENT1)))
        self.info = info
        self.setWindowTitle("发现新版本")
        self.setWindowIcon(make_app_icon())
        self.setMinimumWidth(440)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(12)

        title = QLabel("桌面歌词 有新版本可用")
        title.setObjectName("udtitle")
        v.addWidget(title)

        cur = QLabel("当前 v%s  →  最新 v%s" % (APP_VERSION, info.get("version", "")))
        cur.setObjectName("udsub")
        v.addWidget(cur)

        notes = (info.get("notes") or "").strip()
        if notes:
            te = QTextEdit()
            te.setReadOnly(True)
            te.setPlainText(notes[:3000])
            te.setMaximumHeight(150)
            v.addWidget(te)

        self._gh_url = (info.get("url") or "").strip()
        self._lz_setup = (info.get("lanzou_setup") or "").strip()
        self._lz_portable = (info.get("lanzou_portable") or "").strip()

        chans = []
        if self._lz_setup or self._lz_portable:
            chans.append("蓝奏云（国内直连）")
        if self._gh_url:
            chans.append("GitHub Releases")
        chan_lbl = QLabel("下载渠道：" + " · ".join(chans) if chans
                          else "清单未提供下载链接")
        chan_lbl.setObjectName("udhint")
        chan_lbl.setWordWrap(True)
        v.addWidget(chan_lbl)

        # 主按钮优先蓝奏云安装版（国内下载最快），没有镜像时退回 GitHub 直链
        main_url = self._lz_setup or self._lz_portable or self._gh_url
        main_txt = "蓝奏云下载" if (self._lz_setup or self._lz_portable) else "前往下载"

        btns = QHBoxLayout()
        btns.setSpacing(10)
        later = QPushButton("稍后再说")
        later.setObjectName("udghost")
        later.setCursor(Qt.PointingHandCursor)
        later.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(later)
        if self._gh_url and (self._lz_setup or self._lz_portable):
            gh = QPushButton("GitHub 下载")
            gh.setObjectName("udghost")
            gh.setCursor(Qt.PointingHandCursor)
            gh.clicked.connect(lambda: self._open(self._gh_url))
            btns.addWidget(gh)
        go = QPushButton(main_txt)
        go.setObjectName("udgo")
        go.setCursor(Qt.PointingHandCursor)
        go.clicked.connect(lambda: self._open(main_url))
        btns.addWidget(go)
        v.addLayout(btns)

        # 主按钮已是安装版时，免安装版单独给一个文字链
        if self._lz_setup and self._lz_portable:
            alt = QLabel('<a href="%s">免安装版（蓝奏云）</a>' % self._lz_portable)
            alt.setObjectName("udlink")
            alt.setOpenExternalLinks(True)
            alt.setTextInteractionFlags(Qt.TextBrowserInteraction)
            v.addWidget(alt, 0, Qt.AlignRight)

        self.setStyleSheet(
            "QDialog{background:#14171f;border-radius:14px;}"
            "QLabel#udtitle{color:#f2f6fb;font-size:16px;font-weight:600;}"
            "QLabel#udsub{color:#9fb0c3;font-size:13px;}"
            "QLabel#udhint{color:#9fb0c3;font-size:12px;}"
            "QLabel#udlink{color:%s;font-size:12px;}"
            "QTextEdit{background:#0f1218;color:#cfd8e3;border:1px solid #2a2f3a;"
            "border-radius:8px;padding:8px;font-size:12px;}"
            "QPushButton#udghost{background:transparent;color:#cdd7e3;"
            "border:1px solid #39414e;border-radius:9px;padding:8px 16px;font-size:13px;}"
            "QPushButton#udghost:hover{background:#1d222c;}"
            "QPushButton#udgo{background:%s;color:#06222e;border:none;border-radius:9px;"
            "padding:8px 18px;font-size:13px;font-weight:600;}"
            "QPushButton#udgo:hover{background:%s;}"
            % (accent.name(), accent.name(), accent.lighter(115).name()))

    def _open(self, url: str = ""):
        url = (url or "").strip() or (self.info.get("url") or "").strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        self.accept()


def draw_lock_glyph(p: QPainter, r: QRectF, locked: bool, color: QColor = None):
    """矢量小锁：锁上=闭合锁梁，解锁=锁梁右开（圆角锁体，线面结合）"""
    col = color or QColor(255, 255, 255, 228)
    p.save()
    cx, cy = r.center().x(), r.center().y() + r.height() * 0.07
    u = r.height() * 0.40
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(col, max(1.2, u * 0.17), Qt.SolidLine, Qt.RoundCap))
    p.drawArc(QRectF(cx - u * 0.46, cy - u * 0.92, u * 0.92, u * 1.02),
              0, 180 * 16 if locked else 128 * 16)
    p.setPen(Qt.NoPen)
    c = QColor(col)
    if not locked:
        c.setAlpha(int(col.alpha() * 0.55))
    p.setBrush(c)
    body = QRectF(cx - u * 0.68, cy - u * 0.16, u * 1.36, u * 0.94)
    p.drawRoundedRect(body, u * 0.30, u * 0.30)
    # 锁体上的小孔：解锁时更淡，锁上时更深，靠明暗区分状态
    hole = QColor(12, 14, 18, 190 if locked else 110)
    p.setBrush(hole)
    p.drawEllipse(QPointF(cx, cy + u * 0.30), u * 0.15, u * 0.15)
    p.restore()


def _out_back(u: float) -> float:
    c1, c3 = 1.70158, 2.70158
    u = min(1.0, max(0.0, u))
    return 1.0 + c3 * ((u - 1.0) ** 3) + c1 * ((u - 1.0) ** 2)


def _out_cubic(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return 1.0 - (1.0 - u) ** 3


def _smoothstep(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def karaoke_color(accent: QColor, t: float, dim_alpha: int) -> QColor:
    """逐字卡拉OK的「未唱 → 已唱」取色：t=0 是暗底白字，t=1 是封面主色。

    抽成独立函数是为了让「渐变波前」也能复用同一套取色——正在唱的那个字要沿字宽
    铺一条 t 从 (e-0.5) 到 (e+0.5) 的横向渐变，端点色必须和整字平色用同一算法，
    否则波前处会出现色阶跳变。
    """
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return QColor(int(255 + (accent.red() - 255) * t),
                  int(255 + (accent.green() - 255) * t),
                  int(255 + (accent.blue() - 255) * t),
                  int(dim_alpha + (252 - dim_alpha) * t))


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


class LyricOverlay(QWidget):
    fetched = Signal(object)  # payload=(req_id, lines, words, fallback_cover_bytes)
    update_checked = Signal(object)  # payload={'has_update':bool,'manual':bool,'version':str,'url':str,'notes':str,'msg':str}

    def __init__(self, watcher: MediaWatcher):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("桌面歌词")

        self.cfg = load_config()
        self.song = None
        self.cover_pix = None
        self.lines = []             # [[t, text], ...]
        self.words = {}             # 行号 -> [[t, dur, 词块]...]
        self.trans = []             # [[t, 翻译], ...]
        self._trans_map = {}        # 行号 -> 翻译文本（按时间最近匹配，抓取后构建一次）
        self.cur_idx = -1
        self.anchor_pos = 0.0
        self.anchor_ts = 0.0
        self._last_tick_pos = None   # 上一次收到的播放器原始进度（供连续性校正）
        self._frozen_report = False  # 播放器 SMTC 位置上报是否处于冻结中
        self.duration = 0.0
        self.status = "CLOSED"
        self.click_through = bool(self.cfg.get("click_through", False))
        self.show_cover = bool(self.cfg.get("show_cover", True))
        self.style_mode = self.cfg.get("style", "native")          # native / glass
        self.display_mode = self.cfg.get("display_mode", "desktop")  # desktop / topmost
        self.font_scale = float(self.cfg.get("font_scale", 1.0))     # 0.5 ~ 2.0
        self.font_family = str(self.cfg.get("font_family", "") or "")  # 空 = 默认 MiSans/雅黑
        self.opacity = min(1.0, max(0.3, float(self.cfg.get("opacity", 1.0))))
        self.offset = min(5.0, max(-5.0, float(self.cfg.get("offset", 0.0))))  # 秒，正=歌词提前
        self.anim_style = self.cfg.get("anim_style", "slide")        # slide / zoom / fade / none
        self.edge_fade = bool(self.cfg.get("edge_fade", True))
        self.edge_fade_px = int(self.cfg.get("edge_fade_px", 26))
        self.show_trans = bool(self.cfg.get("show_trans", True))     # 翻译 / 音译歌词
        self.glow = bool(self.cfg.get("glow", True))                 # 封面主色氛围光晕
        self.pause_fade = bool(self.cfg.get("pause_fade", True))     # 暂停自动淡出
        self.show_time = bool(self.cfg.get("show_time", True))       # 进度时间 mm:ss
        self.locked = bool(self.cfg.get("locked", False))            # 锁定位置（禁止拖动）
        self.hotkeys_on = bool(self.cfg.get("hotkeys", False))       # 全局快捷键（默认关闭，避免和别的软件抢键）
        self.keepalive = bool(self.cfg.get("keepalive", True))       # 进程保活（守护进程自动拉起）
        # 更新地址：留空时用内置源（GitHub Releases 查版本 + 蓝奏云镜像下载），开箱即用
        self.update_url = (self.cfg.get("update_url") or "").strip() or DEFAULT_UPDATE_URL
        self.update_auto = bool(self.cfg.get("update_auto", True))     # 启动自动检查更新
        self._update_result = None
        self.update_checked.connect(self._on_update_checked)
        self.idle_saver = bool(self.cfg.get("idle_saver", False))    # 空闲自动进入氛围屏保
        self.idle_min = int(self.cfg.get("idle_min", 10))            # 空闲多少分钟触发（3~60）
        self.saver_idle_only = bool(self.cfg.get("saver_idle_only", True))  # 屏保仅在空闲时启动
        self.saver_style = self.cfg.get("saver_style", "particle")   # 屏保风格: particle(粒子) / minimal(极简)
        self.pos_preset = self.cfg.get("pos_preset", POS_FREE)       # 摆放位置预设 / free=自由拖拽
        self._pos_actions = {}                                       # 摆放位置菜单项（托盘刷新用）
        self._a_pos_free = None

        self.accent1 = QColor(DEFAULT_ACCENT1)
        self.accent2 = QColor(DEFAULT_ACCENT2)
        self.bg_color = pill_bg_color(DEFAULT_ACCENT1)

        self._fill = 0.0
        self._line_t = 1.0
        self._line_anim = QVariantAnimation(self)
        self._line_anim.setDuration(380)
        self._line_anim.setStartValue(0.0)
        self._line_anim.setEndValue(1.0)
        self._line_anim.valueChanged.connect(self._on_line_anim)

        self._size_anim = QPropertyAnimation(self, b"size", self)
        self._size_anim.setDuration(300)
        self._size_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._drag_offset = None
        self._req_id = 0
        self.panel = None           # SettingsPanel 惰性创建
        self._current_text = ""
        self._next_text = ""
        self._spans_cache = {}      # 行号 -> (text, spans)，避免每帧重算逐字时间轴
        self._sig_tick = 0          # 接管哨兵轮询计数（约每 15 帧查一次文件）
        self._cover_scaled = None   # 封面缩放缓存，避免每帧 SmoothTransformation
        self._cover_scaled_size = 0
        self._vinyl_ang = 0.0       # 黑胶旋转角
        self._vinyl_pix = None      # 黑胶中心标签缓存
        self._vinyl_pix_size = 0
        self._ctrl_t = 0.0          # 悬浮控制条透明度（0=隐藏）
        self._hovered = False       # 鼠标是否悬停（悬停时窗口底部为控制条预留一行）
        self._layout_size = (0.0, 0.0)   # 上一次 _relayout 算出的内容尺寸（内容几何真相）
        self._ctrl_anim = QVariantAnimation(self)
        self._ctrl_anim.setDuration(160)
        self._ctrl_anim.valueChanged.connect(self._on_ctrl_anim)
        self._ctrl_setting_up = False   # _animate_ctrl 装弹期间抑制启动脉冲

        self._vinyl_ts = time.monotonic()   # 黑胶按真实时间旋转，低帧率也不抖
        self._glow_ph = 0.0                 # 氛围光晕呼吸相位
        self._last_frame_pos = -1e9         # 上一帧的歌词位置（用于判断"画面是否真的变了"）
        self._pause_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._pause_anim.setDuration(260)
        self._pause_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self.hotkeys = GlobalHotkeys(self)
        self.hotkeys.triggered.connect(self._on_hotkey)

        watcher.mediaChanged.connect(self._apply_media)
        watcher.ticked.connect(self._apply_tick)

        self.fetched.connect(self._on_fetched)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_frame)
        self._timer.start(33)

        self._shadow = QGraphicsDropShadowEffect(self)
        self.setGraphicsEffect(self._shadow)
        self._apply_shadow()

        self._build_tray()
        self._apply_click_through()
        self._apply_display_mode()
        self.setWindowOpacity(self.opacity)
        self._setup_hotkeys()
        self._relayout()
        if self._restore_position():
            self._restore_position_done = True
        self._place_default_if_needed()

        self._zorder_timer = QTimer(self)
        self._zorder_timer.timeout.connect(self._assert_zorder)
        self._zorder_timer.start(900)

        # 保活：确保有守护进程盯着自己（开机自启走 --supervise 时不会重复拉起）
        if self.keepalive:
            spawn_supervisor()

        # 空闲自动进入氛围屏保
        self.saver = None
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._check_idle)
        self._idle_timer.start(15000)

        watcher.activate()

    # ---------------- 字体 ----------------

    def _px(self, v: float) -> float:
        """字号缩放：所有尺寸基准值统一走这里"""
        return v * self.font_scale

    def _font_cur(self, px: float) -> QFont:
        f = QFont(self.font_family or FONT_CUR)
        f.setPixelSize(max(8, int(round(px))))
        f.setBold(CUR_BOLD and not self.font_family)
        return f

    def _font_reg(self, px: float) -> QFont:
        f = QFont(self.font_family or FONT_REG)
        f.setPixelSize(max(8, int(round(px))))
        return f

    def _font_med(self, px: float) -> QFont:
        f = QFont(self.font_family or FONT_MED)
        f.setPixelSize(max(8, int(round(px))))
        return f

    def _fit_font(self, make, base_px: float, text: str, avail: float,
                  min_ratio: float = 0.55):
        """长句自适应：按 5% 逐级缩小字号直到放得下（最低 55%），仍放不下再截断"""
        px = base_px
        while px > base_px * min_ratio:
            f = make(px)
            if QFontMetrics(f).horizontalAdvance(text) <= avail:
                return f, QFontMetrics(f)
            px -= max(1.0, base_px * 0.05)
        f = make(px)
        return f, QFontMetrics(f)

    # ---------------- 位置 / 配置 ----------------

    def _margin(self) -> float:
        return {"native": MARGIN_N, "vinyl": MARGIN_V, "ios": MARGIN_IOS,
                "spotify": MARGIN_SP}.get(self.style_mode, MARGIN)

    def _apply_shadow(self):
        """主题特效策略：所有主题统一为「原生浮字」那套（不挂投影特效）

        原生浮字是最流畅的那个主题——它从 v2.4 起就关掉了 QGraphicsDropShadowEffect
        （省掉每帧的整窗高斯模糊重绘）。其余主题原本各带 16~26px 模糊，在无边框 +
        WA_TranslucentBackground 的窗口上等于每帧多走一遍模糊与合成，逐字动画会被拖住。
        所以这里统一成同一套逻辑：一律不启用投影，卡片靠自身渐变底 + 1px 描边分层。
        详见 `THEME_DROP_SHADOW`。
        """
        if not THEME_DROP_SHADOW:
            self._shadow.setEnabled(False)
            return
        sm = self.style_mode
        if sm == "native":
            self._shadow.setEnabled(False)
            return
        self._shadow.setEnabled(True)
        if sm == "vinyl":
            self._shadow.setBlurRadius(16)
            self._shadow.setOffset(0, 3)
            self._shadow.setColor(QColor(0, 0, 0, 130))
        elif sm == "glass":
            self._shadow.setBlurRadius(22)
            self._shadow.setOffset(0, 5)
            self._shadow.setColor(QColor(0, 0, 0, 150))
        else:  # ios / spotify 卡片
            self._shadow.setBlurRadius(26)
            self._shadow.setOffset(0, 7)
            self._shadow.setColor(QColor(0, 0, 0, 160))

    def _preset_point(self, key: str):
        """按预设算出窗口左上角坐标（相对屏幕安全区，任务栏/分辨率变了也贴得住）"""
        g = QApplication.primaryScreen().availableGeometry()
        w, h, m = self.width(), self.height(), POSITION_MARGIN
        if key == "top":
            return g.x() + (g.width() - w) // 2, g.y() + m
        if key == "center":
            return g.x() + (g.width() - w) // 2, g.y() + (g.height() - h) // 2
        if key == "top_left":
            return g.x() + m, g.y() + m
        if key == "top_right":
            return g.x() + g.width() - w - m, g.y() + m
        if key == "bottom_left":
            return g.x() + m, g.y() + g.height() - h - m
        if key == "bottom_right":
            return g.x() + g.width() - w - m, g.y() + g.height() - h - m
        return g.x() + (g.width() - w) // 2, g.y() + g.height() - h - m   # bottom

    def _apply_position_preset(self, key: str):
        """套用一个位置预设（借鉴 FluentFlyout 的浮层位置定制）"""
        if key not in POSITION_PRESET_NAMES:
            return
        self.pos_preset = key
        self.move(*self._preset_point(key))
        self._restore_position_done = True
        self._save_position()

    def _current_position_key(self) -> str:
        """当前窗口位置对应哪个预设；对不上就是 free（用户自己拖的）"""
        p = self.pos()
        for key, _name in POSITION_PRESETS:
            x, y = self._preset_point(key)
            if abs(p.x() - x) <= 4 and abs(p.y() - y) <= 4:
                return key
        return POS_FREE

    def _restore_position(self):
        preset = self.cfg.get("pos_preset")
        if preset in POSITION_PRESET_NAMES:      # 预设位置优先：跟着当前屏幕重新算
            self.pos_preset = preset
            self.move(*self._preset_point(preset))
            return True
        self.pos_preset = POS_FREE
        x, y = self.cfg.get("x"), self.cfg.get("y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)
            self._clamp_into_screen()            # 换显示器/分辨率后存的坐标可能在屏幕外
            return True
        return False

    def _place_default_if_needed(self):
        if self._restore_position_done:
            return
        self.pos_preset = "bottom"
        self.move(*self._preset_point("bottom"))
        self._restore_position_done = True

    def _save_position(self):
        self.cfg.update(x=self.x(), y=self.y(), click_through=self.click_through,
                        show_cover=self.show_cover, style=self.style_mode,
                        display_mode=self.display_mode, font_scale=self.font_scale,
                        font_family=self.font_family, opacity=self.opacity,
                        offset=self.offset, anim_style=self.anim_style,
                        edge_fade=self.edge_fade, edge_fade_px=self.edge_fade_px,
                        show_trans=self.show_trans, glow=self.glow,
                        pause_fade=self.pause_fade, show_time=self.show_time,
                        locked=self.locked, hotkeys=self.hotkeys_on,
                        keepalive=self.keepalive, idle_saver=self.idle_saver,
                        idle_min=self.idle_min, saver_idle_only=self.saver_idle_only,
                        saver_style=self.saver_style, pos_preset=self.pos_preset)
        save_config(self.cfg)

    # ---------------- 显示模式：常驻桌面 / 置顶悬浮 ----------------

    def _apply_display_mode(self):
        # setWindowFlag 会隐式隐藏窗口，必须先记录可见状态再恢复，否则切换后直接消失
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.display_mode == "topmost")
        if was_visible:
            self.show()

    def _toggle_display_mode(self):
        self.display_mode = "topmost" if self.display_mode == "desktop" else "desktop"
        self._apply_display_mode()
        self._save_position()
        self.tray.showMessage("桌面歌词",
                              "已切换为：%s" % ("置顶悬浮（覆盖窗口）" if self.display_mode == "topmost"
                                              else "常驻桌面（不遮挡窗口）"),
                              QSystemTrayIcon.Information, 1500)

    def _assert_zorder(self):
        """常驻桌面模式：把窗口压到其它普通窗口之下（仍在壁纸/图标之上）"""
        if self.display_mode != "desktop" or not self.isVisible():
            return
        try:
            if self.isMinimized():
                self.setWindowState(Qt.WindowNoState)
            hwnd = int(self.winId())
            HWND_BOTTOM, SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 1, 0x1, 0x2, 0x10
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                                              SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        except Exception:
            pass

    # ---------------- 托盘 ----------------

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip("桌面歌词")
        menu = QMenu()

        act_panel = QAction(make_menu_icon("gear"), "设置面板…", menu)
        act_panel.triggered.connect(self._open_panel)
        act_show = QAction("显示 / 隐藏歌词", menu)
        act_show.triggered.connect(self._toggle_visible)
        act_refetch = QAction(make_menu_icon("refresh"), "重新获取歌词", menu)
        act_refetch.triggered.connect(self._refresh_lyrics)
        menu.addSeparator()

        # 播放控制（一键直达，不用多点）
        m_play = menu.addMenu("播放控制")
        self._a_play = None
        for text, cmd, ico in (("上一首", "prev", "prev"),
                               ("播放 / 暂停", "toggle",
                                "pause" if self.status == "PLAYING" else "play"),
                               ("下一首", "next", "next")):
            a = m_play.addAction(make_menu_icon(ico), text)
            a.triggered.connect(lambda _=False, c=cmd: self.media_command(c))
            if cmd == "toggle":
                self._a_play = a

        m_style = menu.addMenu("样式")
        self._style_actions = {}
        for key, name in STYLE_NAMES.items():
            a = m_style.addAction(name)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self.set_style_mode(k))
            self._style_actions[key] = a

        m_dm = menu.addMenu("显示模式")
        self._a_desktop = m_dm.addAction("常驻桌面（不遮挡窗口）")
        self._a_desktop.setCheckable(True)
        self._a_desktop.triggered.connect(lambda: self.set_display_mode("desktop"))
        self._a_top = m_dm.addAction("置顶悬浮（覆盖窗口）")
        self._a_top.setCheckable(True)
        self._a_top.triggered.connect(lambda: self.set_display_mode("topmost"))

        # 歌词
        m_lyr = menu.addMenu("歌词")
        act_cover = QAction("显示专辑封面", menu)
        act_cover.setCheckable(True)
        act_cover.triggered.connect(self._toggle_cover)
        act_trans = QAction("显示翻译 / 音译", menu)
        act_trans.setCheckable(True)
        act_trans.triggered.connect(lambda: self.set_show_trans(act_trans.isChecked()))
        self._a_off_title = m_lyr.addAction("偏移 %+.1fs（正值为提前）" % self.offset)
        self._a_off_title.setEnabled(False)
        a_early = m_lyr.addAction("提前 0.5 秒")
        a_early.triggered.connect(lambda: self.set_offset(self.offset + 0.5))
        a_late = m_lyr.addAction("延后 0.5 秒")
        a_late.triggered.connect(lambda: self.set_offset(self.offset - 0.5))
        a_zero = m_lyr.addAction("偏移归零")
        a_zero.triggered.connect(lambda: self.set_offset(0.0))
        m_lyr.addSeparator()
        m_lyr.addAction(act_cover)
        m_lyr.addAction(act_trans)

        # 悬浮窗
        m_float = menu.addMenu("悬浮窗")
        act_ct = QAction("鼠标点击穿透", menu)
        act_ct.setCheckable(True)
        act_ct.triggered.connect(self._toggle_click_through)
        act_lock = QAction("锁定位置（禁止拖动）", menu)
        act_lock.setCheckable(True)
        act_lock.triggered.connect(lambda: self.set_locked(act_lock.isChecked()))
        act_glow = QAction("氛围光晕", menu)
        act_glow.setCheckable(True)
        act_glow.triggered.connect(lambda: self.set_glow(act_glow.isChecked()))
        act_pfade = QAction("暂停自动淡出", menu)
        act_pfade.setCheckable(True)
        act_pfade.triggered.connect(lambda: self.set_pause_fade(act_pfade.isChecked()))
        act_time = QAction("显示进度时间", menu)
        act_time.setCheckable(True)
        act_time.triggered.connect(lambda: self.set_show_time(act_time.isChecked()))
        for a in (act_ct, act_lock, act_glow, act_pfade, act_time):
            m_float.addAction(a)

        # 摆放位置（借鉴 FluentFlyout 的浮层位置定制）
        self._build_pos_menu(menu, track=True)

        # 氛围屏保
        m_saver = menu.addMenu("氛围屏保")
        act_saver = QAction("立即进入（黑底）", menu)
        act_saver.triggered.connect(lambda: self.open_saver())
        act_saver_auto = QAction("空闲自动进入", menu)
        act_saver_auto.setCheckable(True)
        act_saver_auto.triggered.connect(lambda: self.set_idle_saver(act_saver_auto.isChecked()))
        m_saver.addAction(act_saver)
        m_saver.addAction(act_saver_auto)
        m_saver.addSeparator()
        # 屏保风格
        m_saver_style = m_saver.addMenu("风格")
        self._saver_style_actions = {}
        for key, name in (("particle", "3D 粒子（星云）"), ("minimal", "极简时钟"),
                          ("bars", "音浪"), ("orbits", "星轨")):
            a = m_saver_style.addAction(name)
            a.setCheckable(True)
            a.triggered.connect(lambda _=False, k=key: self.set_saver_style(k))
            self._saver_style_actions[key] = a
        m_saver.addSeparator()
        for m in (3, 5, 10, 15, 20, 30, 45, 60):
            a = m_saver.addAction("空闲 %d 分钟触发" % m)
            a.triggered.connect(lambda _=False, mm=m: (self.set_idle_saver(True),
                                                       self.set_idle_min(mm)))

        # 系统
        m_sys = menu.addMenu("系统")
        act_auto = QAction("开机自启", menu)
        act_auto.setCheckable(True)
        act_auto.triggered.connect(self._toggle_autostart)
        act_keep = QAction("进程保活（崩溃自动拉起）", menu)
        act_keep.setCheckable(True)
        act_keep.triggered.connect(lambda: self.set_keepalive(act_keep.isChecked()))
        act_hk = QAction("全局快捷键", menu)
        act_hk.setCheckable(True)
        act_hk.triggered.connect(lambda: self.set_hotkeys(act_hk.isChecked()))
        act_about = QAction("关于…", menu)
        act_about.triggered.connect(self._about)
        m_sys.addAction(act_auto)
        m_sys.addAction(act_keep)
        m_sys.addAction(act_hk)
        act_check = QAction("检查更新…", menu)
        act_check.triggered.connect(lambda: self.check_update(manual=True))
        m_sys.addAction(act_check)
        m_sys.addSeparator()
        m_sys.addAction(act_about)

        act_quit = QAction(make_menu_icon("quit"), "退出", menu)
        act_quit.triggered.connect(self._quit)

        menu.addAction(act_panel)
        menu.addAction(act_show)
        menu.addAction(act_refetch)
        menu.addSeparator()
        menu.addMenu(m_play)
        menu.addMenu(m_style)
        menu.addMenu(m_dm)
        menu.addMenu(m_lyr)
        menu.addMenu(m_float)
        menu.addMenu(m_sys)
        menu.addSeparator()
        menu.addAction(act_quit)

        self._a_ct = act_ct
        self._a_cover = act_cover
        self._a_trans = act_trans
        self._a_lock = act_lock
        self._a_glow = act_glow
        self._a_pfade = act_pfade
        self._a_time = act_time
        self._a_auto = act_auto
        self._a_hk = act_hk
        self._a_keep = act_keep
        self._a_check = act_check
        self._a_saver_auto = act_saver_auto
        menu.aboutToShow.connect(self._sync_tray_menu)
        menu.setStyleSheet(menu_qss(self.accent1))
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._toggle_visible() if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

        # 启动后自动检查更新（用户开启且已配置地址时才跑，避免无谓联网）
        if self.update_auto and self.update_url:
            QTimer.singleShot(4000, lambda: self.check_update(manual=False))

    def _sync_tray_menu(self):
        """托盘菜单每次弹出前刷新勾选状态"""
        # 播放 / 暂停那一项的图标跟着状态走（托盘菜单是常驻对象，不重建）
        if getattr(self, "_a_play", None) is not None:
            self._a_play.setIcon(make_menu_icon(
                "pause" if self.status == "PLAYING" else "play"))
        for k, a in self._style_actions.items():
            a.setChecked(self.style_mode == k)
        self._a_desktop.setChecked(self.display_mode == "desktop")
        self._a_top.setChecked(self.display_mode == "topmost")
        self._a_ct.setChecked(self.click_through)
        self._a_cover.setChecked(self.show_cover)
        self._a_trans.setChecked(self.show_trans)
        self._a_lock.setChecked(self.locked)
        self._a_glow.setChecked(self.glow)
        self._a_pfade.setChecked(self.pause_fade)
        self._a_time.setChecked(self.show_time)
        self._a_auto.setChecked(autostart_enabled())
        self._a_hk.setChecked(self.hotkeys_on)
        self._a_keep.setChecked(self.keepalive)
        self._a_saver_auto.setChecked(self.idle_saver)
        for k, a in self._saver_style_actions.items():
            a.setChecked(self.saver_style == k)
        cur_pos = self._current_position_key()
        for k, a in getattr(self, "_pos_actions", {}).items():
            a.setChecked(k == cur_pos)
        if getattr(self, "_a_pos_free", None) is not None:
            self._a_pos_free.setChecked(cur_pos == POS_FREE)
        self._a_off_title.setText("偏移 %+.1fs（正值为提前）" % self.offset)

    def _toggle_autostart(self):
        on = not autostart_enabled()
        if set_autostart(on):
            self.tray.showMessage("桌面歌词", "已%s开机自启" % ("开启" if on else "关闭"),
                                  QSystemTrayIcon.Information, 1500)

    def _about(self):
        # 用 styled_message 而不是 QMessageBox.about()：静态方法起的是系统原生白底对话框，
        # 不继承任何皮肤，会跟整个深色 UI 格格不入。
        styled_message(
            self, "关于 桌面歌词",
            "桌面歌词 v%s" % APP_VERSION,
            "跟随系统媒体播放的卡拉OK歌词悬浮条\n"
            "5 种悬浮样式 · 9 种逐字动画 · 翻译歌词 · 氛围光晕\n"
            "字体库（免费商用字体一键下载）· 氛围屏保（黑底防烧屏）\n"
            "摆放位置预设（7 个锚点，换分辨率也贴边）\n"
            "多源并行抓词 · 启动约 0.2s · 隐藏后不占 CPU\n"
            "柔和描边（浅色/深色壁纸都清晰）· 开机自启 · 进程保活 · 全局快捷键（默认关闭）\n\n"
            "SMTC · QQ音乐 / 网易云 / 酷狗 / LRCLIB · PySide6\n"
            "歌词引擎与优化借鉴 Lyricify-Lyrics-Helper（Apache-2.0），详见 NOTICE.md\n\n"
            "全局快捷键（Ctrl+Alt+…）：P 播放/暂停 · , / . 上下首 · "
            "[ / ] 歌词偏移 · L 显示隐藏 · S 设置 · T 样式 · D 显示模式\n"
            "G 锁定位置 · B 氛围屏保",
            accent=self.accent1)

    # ---------------- 检查更新 ----------------

    def check_update(self, manual: bool = False):
        """检查更新：manual=True 表示用户手动触发（无论有无更新都给提示）；
        manual=False 仅用于启动自动检查（无更新时静默）。"""
        url = self.update_url or DEFAULT_UPDATE_URL
        if not url:
            if manual:
                self.tray.showMessage(
                    "桌面歌词",
                    "未配置更新地址：请在「设置 → 系统 → 更新地址」填写 "
                    "GitHub Releases 或更新清单链接。",
                    QSystemTrayIcon.Information, 4500)
            return
        # 网络请求放后台线程，避免卡 UI
        threading.Thread(target=self._check_update_worker,
                         args=(url, manual), daemon=True).start()

    def _check_update_worker(self, url: str, manual: bool):
        """依次尝试各个更新源，取版本号最高的有效结果。

        主源是 GitHub Releases；GitHub 在国内可能访问不畅，所以额外挂了
        国内可直连的清单镜像（仓库里的 update.json，自带蓝奏云链接）。
        任一源失败只记下错误、继续下一个，全部失败才提示失败。
        """
        best, err, got_data = None, "", False
        for src in [url] + list(UPDATE_FALLBACK_SOURCES):
            try:
                api_url = resolve_update_url(src)
                if not api_url:
                    continue
                data = http_get(api_url, timeout=8.0)
                got_data = True
                info = parse_update_payload(data, api_url)
                if not info or not info.get("version"):
                    continue
                # 补上内置蓝奏云镜像（清单自带镜像时不覆盖，优先用清单里的）
                mir = lanzou_mirror(info["version"])
                for k, label in (("lanzou_setup", "setup"), ("lanzou_portable", "portable")):
                    if not info.get(k) and mir.get(label):
                        info[k] = mir[label]
                if not info.get("url"):
                    info["url"] = GITHUB_RELEASES_PAGE
                if best is None or compare_version(info["version"], best["version"]) > 0:
                    best = info
            except Exception as ex:
                err = str(ex)
        if best is None:
            msg = ("更新信息格式无法识别（请确认链接返回的是合法 JSON）。"
                   if got_data and not err else "检查更新失败：%s" % (err or "网络不可用"))
            self.update_checked.emit({"has_update": False, "manual": manual, "msg": msg})
            return
        if compare_version(best["version"], APP_VERSION) <= 0:
            self.update_checked.emit({
                "has_update": False, "manual": manual,
                "msg": "当前已是最新版本 v%s" % APP_VERSION})
            return
        best.update({"has_update": True, "manual": manual})
        self.update_checked.emit(best)

    def _on_update_checked(self, payload):
        """在主线程处理检查结果（信号跨线程走 QueuedConnection 回到主线程）"""
        if not isinstance(payload, dict):
            return
        if payload.get("has_update"):
            self._update_result = payload
            ver = payload.get("version", "")
            self.tray.showMessage(
                "桌面歌词",
                "发现新版本 v%s，点击「前往下载」升级" % ver,
                QSystemTrayIcon.Information, 6000)
            self._show_update_dialog(payload)
            return
        # 无更新 / 出错 / 未配置：仅手动检查时提示
        if payload.get("manual") and payload.get("msg"):
            self.tray.showMessage("桌面歌词", payload["msg"],
                                  QSystemTrayIcon.Information, 3500)

    def _show_update_dialog(self, info):
        dlg = UpdateDialog(self, info)
        dlg.exec()

    def set_update_url(self, url: str):
        raw = (url or "").strip()
        self.cfg["update_url"] = raw          # 留空存档 = 用内置源
        self.update_url = raw or DEFAULT_UPDATE_URL
        save_config(self.cfg)

    def set_update_auto(self, on: bool):
        self.update_auto = bool(on)
        self.cfg["update_auto"] = self.update_auto
        save_config(self.cfg)

    # ---------------- 氛围屏保 ----------------

    def _check_idle(self):
        """空闲到达阈值时自动进入氛围屏保；锁屏时不重复起（Windows 自己会息屏）"""
        if not self.idle_saver or self.saver is not None:
            return
        if session_locked():
            return
        if idle_seconds() >= self.idle_min * 60:
            self.open_saver(auto=True)

    def open_saver(self, auto: bool = False):
        if self.saver is not None:
            self.saver.raise_()
            return
        self.saver = AmbientSaver(self)
        self.saver.finished.connect(self._on_saver_closed)
        self.saver.start()
        if not auto:
            self.tray.showMessage("桌面歌词", "氛围屏保已开启 · 按任意键或点击退出",
                                  QSystemTrayIcon.Information, 1800)

    def _on_saver_closed(self):
        self.saver = None

    def close_saver(self):
        if self.saver is not None:
            self.saver.finish()

    def _toggle_visible(self):
        self.setVisible(self.isHidden())
        self._save_position()

    def _toggle_click_through(self):
        self.click_through = not self.click_through
        self._apply_click_through()
        self._save_position()

    def _apply_click_through(self):
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, self.click_through)
        if was_visible:
            self.show()

    def _toggle_cover(self):
        self.show_cover = not self.show_cover
        self._save_position()
        self._relayout()

    def _toggle_style(self):
        order = list(STYLE_NAMES.keys())
        self.style_mode = order[(order.index(self.style_mode) + 1) % len(order)]
        self._apply_shadow()
        self._save_position()
        self._relayout()

    def _reset_position(self):
        self.cfg.pop("x", None)
        self.cfg.pop("y", None)
        self._restore_position_done = False
        self._place_default_if_needed()
        self._save_position()

    def _set_pos_free(self):
        """标记为自由摆放：只记住当前坐标，不再跟着预设走"""
        self.pos_preset = POS_FREE
        self._save_position()

    def _build_pos_menu(self, parent, track: bool = False):
        """「摆放位置」子菜单（借鉴 FluentFlyout 的可定制浮层位置）

        选中项按当前窗口位置反查，所以手动拖过之后会自动落到"自由摆放"上。
        track=True 时把 action 存起来，供托盘菜单弹出前刷新勾选（右键菜单每次重建，不用存）。
        """
        m = parent.addMenu("摆放位置")
        cur = self._current_position_key()
        seen = {}
        for key, name in POSITION_PRESETS:
            a = QAction(name, m)
            a.setCheckable(True)
            a.setChecked(key == cur)
            a.triggered.connect(lambda _checked=False, k=key: self._apply_position_preset(k))
            m.addAction(a)
            seen[key] = a
        m.addSeparator()
        a_free = QAction("自由摆放（记住当前位置）", m)
        a_free.setCheckable(True)
        a_free.setChecked(cur == POS_FREE)
        a_free.triggered.connect(self._set_pos_free)
        m.addAction(a_free)
        m.addSeparator()
        a_reset = QAction("重置为默认位置", m)
        a_reset.triggered.connect(self._reset_position)
        m.addAction(a_reset)
        if track:
            self._pos_actions = seen
            self._a_pos_free = a_free
        return m

    def _quit(self):
        self._save_position()
        # 主动退出＝真的退出：先写停机哨兵，免得守护进程把「正常退出」当成崩溃又拉起来
        if self.keepalive or supervisor_alive():
            stop_supervisor()
        try:
            self.hotkeys.unregister()
        except Exception:
            pass
        self.tray.hide()
        QApplication.quit()

    # ---------------- 设置项（面板 / 菜单共用） ----------------

    def set_font_scale(self, v: float):
        self.font_scale = min(2.0, max(0.5, v))
        self._save_position()
        self._relayout()

    def set_font_family(self, name: str):
        self.font_family = name or ""
        self._save_position()
        self._relayout()

    def set_opacity(self, v: float):
        self.opacity = min(1.0, max(0.3, v))
        self._apply_pause_opacity(anim=False)
        self._save_position()

    def set_offset(self, v: float):
        self.offset = min(5.0, max(-5.0, v))
        self._save_position()

    def set_anim_style(self, key: str):
        if key in ANIM_STYLES:
            self.anim_style = key
            self._line_t = 1.0
            self._save_position()
            self.update()

    def set_edge_fade(self, on: bool, px: int):
        self.edge_fade = bool(on)
        self.edge_fade_px = min(60, max(0, int(px)))
        self._save_position()
        self.update()

    def _apply_accent_ui(self):
        """封面主色变化后，同步面板与托盘菜单的配色"""
        if self.panel is not None:
            self.panel.update_accent(self.accent1)
        try:
            self._tray_menu.setStyleSheet(menu_qss(self.accent1))
        except Exception:
            pass

    def set_style_mode(self, mode: str):
        if mode in STYLE_NAMES and mode != self.style_mode:
            self.style_mode = mode
            self._apply_shadow()
            # 切换主题后文字度量 / 可用宽度会变，旧缓存会让高亮错位或「只亮前几个字」；
            # 同时复位切行动画，避免上一行的入场动画卡在 0（整行透明 = 看似冻结）
            self._spans_cache.clear()
            self._line_t = 1.0
            if self.cur_idx >= 0 and self.lines:
                self._line_anim.stop()
                self._line_anim.start()
            self._save_position()
            self._relayout()
            self.update()

    def set_display_mode(self, mode: str):
        if mode in ("desktop", "topmost") and mode != self.display_mode:
            self.display_mode = mode
            self._apply_display_mode()
            self._save_position()

    def set_show_cover(self, on: bool):
        self.show_cover = bool(on)
        self._save_position()
        self._relayout()

    def set_click_through(self, on: bool):
        self.click_through = bool(on)
        self._apply_click_through()
        self._save_position()

    def set_show_trans(self, on: bool):
        self.show_trans = bool(on)
        self._trans_map = self._build_trans_map() if self.show_trans else {}
        self._save_position()
        self._relayout()

    def set_glow(self, on: bool):
        self.glow = bool(on)
        self._save_position()
        self.update()

    def set_pause_fade(self, on: bool):
        self.pause_fade = bool(on)
        self._apply_pause_opacity(anim=False)
        self._save_position()

    def set_show_time(self, on: bool):
        self.show_time = bool(on)
        self._save_position()
        self._relayout()

    def set_locked(self, on: bool):
        self.locked = bool(on)
        if self.locked:
            self._drag_offset = None
        self._save_position()
        self.update()

    def set_hotkeys(self, on: bool):
        self.hotkeys_on = bool(on)
        self._save_position()
        self._setup_hotkeys(notify=True)

    def set_keepalive(self, on: bool):
        self.keepalive = bool(on)
        self._save_position()
        if self.keepalive:
            spawn_supervisor()      # 拉起守护进程（已存在则是空操作）
        else:
            stop_supervisor()       # 写停机哨兵，守护进程自然退出

    def set_idle_saver(self, on: bool):
        self.idle_saver = bool(on)
        self._save_position()

    def set_idle_min(self, minutes: int):
        self.idle_min = min(60, max(3, int(minutes)))
        self._save_position()

    def set_saver_idle_only(self, on: bool):
        self.saver_idle_only = bool(on)
        self._save_position()

    def set_saver_style(self, key: str):
        if key in ("particle", "minimal", "bars", "orbits") and key != self.saver_style:
            self.saver_style = key
            self._save_position()
            # 切换即时生效：屏保若正显示则立刻按新风格重绘（不依赖下一帧定时器）
            if self.saver is not None:
                self.saver.update()
            # 同步托盘「风格」子菜单的单选勾选（QAction 自动 toggle 会多选，这里强制唯一）
            for k, a in getattr(self, "_saver_style_actions", {}).items():
                a.setChecked(k == key)

    def _toggle_lock(self):
        self.set_locked(not self.locked)
        self.tray.showMessage("桌面歌词", "已%s位置锁定" % ("开启" if self.locked else "关闭"),
                              QSystemTrayIcon.Information, 1200)

    def media_command(self, cmd: str):
        send_media_command(cmd)

    def _refresh_lyrics(self):
        """清掉当前歌曲缓存后重新抓取（歌词匹配错误时手动纠正）"""
        if not self.song:
            return
        try:
            key = ("%s|%s" % (clean_query_text(self.song.get("title") or ""),
                              clean_query_text(self.song.get("artist") or ""))).lower().strip()
            cp = _cache_path(key)
            if os.path.exists(cp):
                os.remove(cp)
        except OSError:
            pass
        self.lines, self.words, self.trans = [], {}, []
        self._trans_map = {}
        self._reset_line_state()
        self._spans_cache.clear()
        self.tray.showMessage("桌面歌词", "正在重新获取歌词…",
                              QSystemTrayIcon.Information, 1200)
        self._start_fetch(self.song)

    # ---------------- 全局快捷键 ----------------

    def _setup_hotkeys(self, notify: bool = False):
        if not self.hotkeys_on:
            self.hotkeys.unregister()
            return
        if self.hotkeys.register() and notify:
            # 注册在后台线程完成，稍等再汇报结果
            QTimer.singleShot(900, self._report_hotkeys)

    def _report_hotkeys(self):
        n = len(self.hotkeys._ids)
        busy = self.hotkeys._failed
        if n == 0:
            msg = "全局快捷键未能启用（组合键被其它程序占用）"
        elif busy:
            msg = "已启用 %d 项；%s 被占用" % (n, " ".join(busy))
        else:
            msg = "全局快捷键已启用（共 %d 项：Ctrl+Alt+P 播放 / 暂停）" % n
        self.tray.showMessage("桌面歌词", msg, QSystemTrayIcon.Information, 2600)

    def _on_hotkey(self, act: str):
        if act == "toggle":
            self.media_command("toggle")
        elif act == "prev":
            self.media_command("prev")
        elif act == "next":
            self.media_command("next")
        elif act == "early":
            self.set_offset(self.offset + 0.5)
        elif act == "late":
            self.set_offset(self.offset - 0.5)
        elif act == "show":
            self._toggle_visible()
        elif act == "panel":
            self._open_panel()
        elif act == "style":
            self._toggle_style()
        elif act == "mode":
            self._toggle_display_mode()
        elif act == "lock":
            self._toggle_lock()
        elif act == "saver":
            self.open_saver()

    def _open_panel(self):
        if self.panel is None:
            self.panel = SettingsPanel(self)
        self.panel.refresh()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    # ---------------- 媒体回调 ----------------

    def _reset_line_state(self):
        """切歌 / 清空媒体时把行状态一起清掉。

        旧版只把 cur_idx 归 -1、不清 _current_text/_next_text，于是新歌歌词还没
        抓回来时（self.lines == []，主循环整段跳过），上一首的最后一句会以
        当前行的形态画在新歌的歌名/占位位置上 —— 正是"歌词叠到歌名上"的来源之一。
        """
        self.cur_idx = -1
        self._current_text = ""
        self._next_text = ""

    def _apply_media(self, info):
        if info is None:
            self.song = None
            self.cover_pix = None
            self.lines = []
            self.words = {}
            self.trans = []
            self._trans_map = {}
            self._reset_line_state()
            self.duration = 0.0
            self.status = "CLOSED"
            self._spans_cache.clear()
            self.tray.setToolTip("桌面歌词：等待播放")
            self._apply_pause_opacity()
            self._relayout()
            return
        self.song = info
        self.lines = []
        self.words = {}
        self.trans = []
        self._trans_map = {}
        self._reset_line_state()
        self._fill = 0.0
        self._last_tick_pos = None
        self._spans_cache.clear()
        if info.get("cover"):
            pix = QPixmap()
            if pix.loadFromData(info["cover"]):
                self.cover_pix = pix
            else:
                self.cover_pix = None
        else:
            self.cover_pix = None
        self._cover_scaled = None
        self._vinyl_pix = None
        self.accent1, self.accent2 = extract_accent(self.cover_pix)
        self.bg_color = pill_bg_color(self.accent1)
        self._apply_accent_ui()
        self.tray.setToolTip("桌面歌词：%s - %s" % (info.get("title"), info.get("artist")))
        self._relayout()
        self._start_fetch(info)

    def _apply_tick(self, pos, duration, status):
        """播放器进度回调（约 0.5s 一次）。

        歌词/进度条都从 anchor 外推出实时值（_current_pos），而不是直接用播放器
        每条原始 pos —— 这样歌词在两次 tick 之间也平滑走字、进度条平滑前进。
        watcher 发出的 pos 经 `_live_pos` 直传（已是播放器给的当前进度本身——
        v2.4.9 曾在这里按 (now - last_updated_time) 外推，反而因双重计数把歌词
        整体带快、连默认主题都不同步；v2.4.12 回退为直传）。SMTC「position 是快照」
        的语义由本方法的锚点外推换算成平滑实时进度，冻结/抖跳统一在此处理，源头无需补偿。
        但部分播放器（尤其网易云 SMTC）的 position 仍会在 0~0.5s 抖动甚至来回跳，
        导致歌词"一格一格跳"。这里做连续性校正：
          · 正常前进（差值 ≤ 2.5s）：不重置锚点，让本地外推继续，消除抖跳；
          · 明显向前跳变（切歌/快进/拖进度条）：重新锚定；
          · 大幅回退（拖回/暂停后恢复）：重新锚定；
          · **上报冻结**（音乐在放但播放器上报的位置不动）：直接忽略本次上报。
            否则本地外推每超前 2.5s 就被拽回冻结值一次，进度变成原地锯齿——
            时间不走、高亮反复点亮行首几个字又弹回，正是「卡住」的来源。
        中间地带（上报比外推落后 2.5~8s）多是上报延迟，信任本地外推不回拽。
        """
        prev = self.status
        self.duration = duration if duration > 0 else self.duration
        self.status = status
        now = time.monotonic()

        da = self._last_tick_pos is None
        if not da and self.status == "PLAYING":
            dt = now - self.anchor_ts
            expect = self.anchor_pos + dt if self.anchor_ts else pos
            err = pos - expect
            # 上报冻结：上报值纹丝不动、且已落后本地外推 → 忽略，继续外推
            if abs(pos - self._last_tick_pos) < 0.1 and err < -1.0:
                if not self._frozen_report:
                    self._frozen_report = True
                    log("播放器位置上报冻结（status=%s 值停在 %.1f，落后外推 %.1fs），忽略上报继续外推"
                        % (status, pos, -err))
                self._last_tick_pos = pos
                if status != prev:
                    self._apply_pause_opacity()
                return
            if self._frozen_report:
                self._frozen_report = False
                log("播放器位置上报恢复: pos=%.1f" % pos)
            if err > 2.5:
                da = True              # 向前跳变：硬对齐
            elif err < -8.0:
                da = True              # 大幅回退：硬对齐
        elif self.status != "PLAYING":
            # 暂停/停止：直接锁死，不随时间走
            self.anchor_pos = pos
            self.anchor_ts = now
        if da:
            self.anchor_pos = pos
            self.anchor_ts = now
        self._last_tick_pos = pos
        if status != prev:
            self._apply_pause_opacity()

    def _start_fetch(self, info):
        self._req_id += 1
        req_id = self._req_id
        title, artist = info.get("title") or "", info.get("artist") or ""
        prefer_netease = "cloudmusic" in (info.get("source") or "").lower()
        duration = max(0.0, float(info.get("duration") or 0.0))

        def worker():
            lines, words, cover_url, trans = fetch_lyrics(title, artist,
                                                          prefer_netease=prefer_netease,
                                                          duration=duration)
            fallback_cover = None
            if self._req_id == req_id and self.cover_pix is None and cover_url:
                try:
                    fallback_cover = http_get(cover_url, timeout=5)
                except Exception:
                    fallback_cover = None
            self.fetched.emit((req_id, lines, words, fallback_cover, trans))

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetched(self, payload):
        req_id, lines, words, fallback_cover, trans = payload
        if req_id != self._req_id:
            return
        self.lines = lines
        self.words = words
        self.trans = trans or []
        self._trans_map = self._build_trans_map()
        self._reset_line_state()
        self._spans_cache.clear()
        if self.cover_pix is None and fallback_cover:
            pix = QPixmap()
            if pix.loadFromData(fallback_cover):
                self.cover_pix = pix
                self._cover_scaled = None
                self._vinyl_pix = None
                self.accent1, self.accent2 = extract_accent(pix)
                self.bg_color = pill_bg_color(self.accent1)
                self._apply_accent_ui()
        self._relayout()

    # ---------------- 翻译歌词 / 暂停淡出 ----------------

    def _build_trans_map(self) -> dict:
        """行号 -> 翻译文本：按时间最近（±1.2s）匹配，原文与译文相同的丢弃"""
        if not self.show_trans or not self.trans or not self.lines:
            return {}
        out = {}
        for i, (t, txt) in enumerate(self.lines):
            best, bd = "", 1.2
            for tt, tx in self.trans:
                d = abs(tt - t)
                if d < bd:
                    bd, best = d, tx
            if best and norm_text(best) != norm_text(txt):
                out[i] = best
        return out

    def _trans_for(self, idx: int) -> str:
        return self._trans_map.get(idx, "")

    def _apply_pause_opacity(self, anim: bool = True):
        """暂停时把窗口整体淡下来，播放时恢复（音频软件的通用做法）；空闲等待态保持正常亮度"""
        keep = (self.status == "PLAYING") or (self.song is None) or (not self.pause_fade)
        target = self.opacity if keep else max(0.28, self.opacity * 0.5)
        if not anim:
            self._pause_anim.stop()
            self.setWindowOpacity(target)
            return
        if abs(self.windowOpacity() - target) < 0.02:
            return
        self._pause_anim.stop()
        self._pause_anim.setStartValue(self.windowOpacity())
        self._pause_anim.setEndValue(target)
        self._pause_anim.start()

    @staticmethod
    def _fmt_time(sec: float) -> str:
        sec = max(0, int(sec))
        return "%d:%02d" % (sec // 60, sec % 60)

    # ---------------- 主循环 ----------------

    def _current_pos(self) -> float:
        if self.status == "PLAYING":
            return self.anchor_pos + (time.monotonic() - self.anchor_ts)
        return self.anchor_pos

    def _lyric_pos(self) -> float:
        """歌词时间轴位置 = 真实进度 + 用户偏移（正值让歌词提前出现）"""
        return self._current_pos() + self.offset

    def _on_line_anim(self, v):
        self._line_t = v
        self.update()

    def _apply_line_anim(self, p: QPainter):
        """切行动画：按所选样式对整行做变换（逐字上浮始终保留）"""
        t = self._line_t
        if self.anim_style == "none" or t >= 0.999:
            return
        if self.anim_style == "zoom":
            e = 0.86 + 0.14 * _out_back(t)
            c = QPointF(self.width() / 2, self.height() / 2)
            p.translate(c)
            p.scale(e, e)
            p.translate(-c)
            p.setOpacity(p.opacity() * _smoothstep(t))
        elif self.anim_style in ("fade", "pop", "wave", "fan", "typer"):
            # 这几种效果由 _draw_karaoke 逐字完成，整行只做柔和淡入
            p.setOpacity(p.opacity() * _smoothstep(t))
        else:  # slide / rise：流光滑入
            p.translate(0, (1.0 - _out_cubic(t)) * 12.0)
            p.setOpacity(p.opacity() * _smoothstep(t))

    def _set_rate(self, ms: int):
        """动态帧率：播放/动画时 30fps，暂停或等待时降到低频，省 CPU"""
        if self._timer.interval() != ms:
            self._timer.setInterval(ms)

    def _needs_repaint(self) -> bool:
        """本帧是否真的需要重绘

        旧实现每帧无脑 update()：暂停时画面一秒都没变，却照样按 10fps 让 Qt 走完
        整套「半透明窗 + 投影 + 圆角裁剪」的合成；窗口隐藏了也照跑（实测仍有 1.6% CPU）。
        这里逐项问一句「到底有没有东西在动」，没有就一个像素都不画。
        """
        if not self.isVisible():
            return False
        if not self.song:
            return True                      # 等待态有呼吸动画
        if self.status == "PLAYING":
            return True                      # 进度 / 逐字 / 黑胶 / 光晕都在动
        return (self._line_anim.state() == QVariantAnimation.Running
                or self._size_anim.state() == QPropertyAnimation.Running
                or self._pause_anim.state() == QPropertyAnimation.Running
                or self._ctrl_anim.state() == QVariantAnimation.Running)

    def _cursor_global(self) -> QPoint:
        """全局光标位置。单独包一层：测试要打桩（PySide6 原生类型的
        静态方法没法 monkeypatch），轮询逻辑也因此可测。"""
        return QCursor.pos()

    def _on_frame(self):
        # 悬停淡出靠轮询而不是 leaveEvent（原因见 leaveEvent 注释）：
        # 光标真的出了窗口矩形才开始收胶囊，落在透明间隙上时保持悬停。
        if self._hovered and not self.frameGeometry().contains(self._cursor_global()):
            self._animate_ctrl(0.0)
        self._sig_tick += 1
        if self._sig_tick >= 15:
            self._sig_tick = 0
            if os.path.exists(RESTART_SIG):
                ver = "?"
                try:
                    with open(RESTART_SIG, encoding="utf-8") as f:
                        first = (f.readline() or "").strip()
                    if "ver=" in first:
                        ver = first.split("ver=", 1)[1].split()[0]
                except OSError:
                    pass
                log("收到 v%s 接管请求，当前 v%s 退出让位" % (ver, APP_VERSION))
                try:
                    os.remove(RESTART_SIG)
                except OSError:
                    pass
                self._quit()
                return
        if not self.song:
            self._set_rate(150)
            if self._needs_repaint():
                self.update()  # 等待态呼吸动画
            return
        pos = self._lyric_pos()
        changed = abs(pos - self._last_frame_pos) > 0.02   # 时间轴动了 → 逐字高亮要跟着动
        self._last_frame_pos = pos
        if self.lines:
            idx = -1
            for i, (t, _) in enumerate(self.lines):
                if t <= pos:
                    idx = i
                else:
                    break
            if idx == -1:
                idx = 0
                current, nxt = self._prelude_texts()
            else:
                current = self.lines[idx][1]
                nxt = self.lines[idx + 1][1] if idx + 1 < len(self.lines) else ""
            # 触发条件必须带上「文本变了」：换歌/重抓词后行号可能相同而文本不同
            if idx != self.cur_idx or current != self._current_text:
                self.cur_idx = idx
                self._current_text = current
                self._next_text = nxt
                self._fill = 0.0
                self._relayout()
                changed = True
                if self.anim_style == "none":
                    self._line_t = 1.0
                else:
                    self._line_anim.stop()
                    self._line_anim.start()
        animating = (self._line_anim.state() == QVariantAnimation.Running
                     or self._size_anim.state() == QPropertyAnimation.Running)
        now = time.monotonic()
        dt = min(0.2, now - self._vinyl_ts)
        self._vinyl_ts = now
        if self.style_mode == "vinyl" and self.status == "PLAYING":
            # 33⅓ 转/分 ≈ 200°/s，取 1/8 速更耐看；按真实时间积分，帧率变化也不抖
            self._vinyl_ang = (self._vinyl_ang + dt * 25.0) % 360.0
        if self.glow and self.status == "PLAYING":
            self._glow_ph = (self._glow_ph + dt * 0.9) % (math.pi * 2)
        if self.status == "PLAYING" or animating:
            self._set_rate(33)
        elif self._needs_repaint():
            self._set_rate(100)
        else:
            # 完全静止（暂停且无动画）：定时器只做低频巡检，画面由「变化」驱动重绘
            self._set_rate(250)
        if changed or self._needs_repaint():
            self.update()

    def _line_fraction(self) -> float:
        if self.cur_idx < 0 or self.cur_idx >= len(self.lines):
            return 0.0
        t0 = self.lines[self.cur_idx][0]
        if self.cur_idx + 1 < len(self.lines):
            t1 = self.lines[self.cur_idx + 1][0]
        else:
            t1 = t0 + 8.0
        if t1 <= t0:
            return 1.0
        return (self._lyric_pos() - t0) / (t1 - t0)

    # ---------------- 逐字时间轴 ----------------

    def _char_spans(self, idx: int, text: str):
        """返回每个字符的 (起, 止) 秒；无逐字数据时按行内均匀分布（结果按行缓存）"""
        cached = self._spans_cache.get(idx)
        if cached is not None and cached[0] == text:
            return cached[1]
        spans = self._build_char_spans(idx, text)
        self._spans_cache[idx] = (text, spans)
        return spans

    def _build_char_spans(self, idx: int, text: str):
        n = len(text)
        spans = [None] * n
        wl = self.words.get(idx) or []
        k = 0
        for (t0, dur, chunk) in wl:
            L = max(1, len(chunk))
            for j in range(L):
                if k >= n:
                    break
                spans[k] = (t0 + dur * (j / L), t0 + dur * ((j + 1) / L))
                k += 1
        missing = [i for i in range(n) if spans[i] is None]
        if missing:
            line_t0 = self.lines[idx][0]
            line_t1 = self.lines[idx + 1][0] if idx + 1 < len(self.lines) else line_t0 + 8.0
            covered = [s for s in spans if s is not None]
            if covered:
                start = max(s[1] for s in covered)
                # 逐字数据本身若已接近/超出行尾，先夹回来，否则后面全排到行外
                start = min(start, max(line_t0, line_t1 - 0.5))
            else:
                start = line_t0
            # 关键：未覆盖到的字必须在「本行结束前」唱完。
            # 旧逻辑是从 start 再往后摊固定 spread 秒，会溢出到下一行的时间轴上，
            # 导致后半句永远点不亮 —— 表现为「只亮前几个字就跳下一行」。
            end_by = max(start + 0.30, line_t1 - 0.15)
            remain = end_by - start
            for j, i in enumerate(missing):
                spans[i] = (start + remain * j / len(missing),
                            start + remain * (j + 1) / len(missing))
        self._fit_spans_to_line(spans, idx)
        return spans

    def _fit_spans_to_line(self, spans, idx):
        """把逐字时间轴等比缩放，铺满「行的实际时长」。

        逐字数据（网易云 YRC / 增强 LRC）通常只标到人声唱完为止，而行的时间戳
        一直排到下一句开始（中间常夹着尾奏、间奏，一句话唱完挂着几十秒很常见）。
        两者对不齐时，高亮会在行首一两秒就全部点亮，然后整行静止到换行 ——
        看上去就是「进度三四秒才更新一次」「看不到播放到哪了」。

        这里保持每个字之间的相对节奏不变，把整段跨度等比拉伸到行时长
        （尾部留 8% 余韵），让高亮像进度条一样从头到尾持续推进。
        本来就贴合的时间轴（ratio 0.90~1.05）不动；拉伸不设上限——
        「高亮贴着播放进度走」比「贴着人声走」更重要，人声只占行首
        一小截时长，按人声走就等于行尾长时间静止。
        """
        cov = [s for s in spans if s is not None]
        if len(cov) < 2 or idx < 0 or idx >= len(self.lines):
            return
        t0 = self.lines[idx][0]
        t1 = self.lines[idx + 1][0] if idx + 1 < len(self.lines) else t0 + 8.0
        span = t1 - t0
        if span <= 0.4:
            return
        ws = min(s[0] for s in cov)
        we = max(s[1] for s in cov)
        if we <= ws:
            return
        ratio = (we - ws) / span
        if 0.90 <= ratio <= 1.05:          # 本来就跟行时长贴合，别去动它
            return
        scale = (span * 0.92) / (we - ws)
        scale = max(0.5, min(30.0, scale))  # 下限防数据毛刺；上限只挡荒谬值
        for i, s in enumerate(spans):
            if s is None:
                continue
            spans[i] = (t0 + (s[0] - ws) * scale, t0 + (s[1] - ws) * scale)
        # 逐字数据可能整体早于/晚于行时间戳，缩放后仍可能探到下一行，收一下尾
        tail = max(s[1] for s in spans if s is not None)
        if tail > t1 - 0.05:
            k = max(0.05, (t1 - 0.05 - t0) / max(0.05, tail - t0))
            for i, s in enumerate(spans):
                if s is None:
                    continue
                spans[i] = (t0 + (s[0] - t0) * k, t0 + (s[1] - t0) * k)

    def _accent_at(self, t: float) -> QColor:
        t = min(1.0, max(0.0, t))
        a, b = self.accent1, self.accent2
        return QColor(int(a.red() + (b.red() - a.red()) * t),
                      int(a.green() + (b.green() - a.green()) * t),
                      int(a.blue() + (b.blue() - a.blue()) * t))

    def _halo_pens(self, w: float) -> tuple:
        """柔和描边：宽而淡的外圈 + 细而深的内圈，两层叠出「落影」而非「马克笔」。

        v2.4.16 之前是单层 `QPen(黑, alpha=170, w)`。实测在浅色桌面上，单层实心描边
        会糊成一圈厚重的黑边，字看着发脏发糊（对比 iOS 主题——它一直是 halo_on=False，
        所以反而最耐看）。现在改成两层：外层 alpha 只有 50 上下，只负责把字从壁纸上
        「托」起来；内层才负责边缘清晰度。多一次 strokePath，代价用
        `_diag_theme_perf.py` 量过（每帧 <0.4ms，占 33ms 预算的 1%）。

        注意：Qt 的 strokePath 是沿轮廓**居中**描边，紧随其后的 fillPath 会盖掉内半边，
        所以每层实际可见的向外延伸 ≈ 该层宽度的一半。

        返回按绘制顺序排列的 (外层, 内层)；w <= 0 时返回空元组（调用方无需特判）。
        """
        if w <= 0:
            return ()
        # 参数是照「浅底 + 深底都要能立住」调的，别只对着一种底色改：
        #  · 外层如果又宽又淡（如 w*1.95 @ alpha 52），在**浅色壁纸**上会摊成一片灰雾，
        #    字看着像失焦——第一版就踩了这个坑。收紧到 1.45 倍再加不透明度才对。
        #  · 深色壁纸上外层几乎看不见，全靠内层定边缘，所以内层要够实。
        outer = QPen(QColor(0, 0, 0, 88), w * 1.45)
        inner = QPen(QColor(0, 0, 0, 150), w * 0.88)
        for pen in (outer, inner):
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
        return (outer, inner)

    def _on_ctrl_anim(self, v):
        if self._ctrl_setting_up:
            # QVariantAnimation 在 setEndValue（甚至 state 还是 Stopped 时）会
            # 同步发一次 valueChanged(起始值)——从 ctrl_t=0 淡入时这个值就是
            # 0.0，旧判定把它当成「淡出结束」，立刻复位 _hovered 并收回 48px
            # 预留行，结果窗口塌回矮高度、胶囊却淡到全不透明，36px 只露出几
            # 像素（用户看到的「控制条只展开一半」）。装弹期间的脉冲一律忽略。
            return
        self._ctrl_t = v
        if v <= 0.0 and self._hovered:
            # 悬停结束：等胶囊完全淡出之后才收回底部预留行，
            # 否则胶囊会在收缩过程中叠回歌词上淡出（旧版就是这么闪的）
            self._hovered = False
            self._relayout()
        self.update()

    def _animate_ctrl(self, target: float):
        self._ctrl_setting_up = True
        try:
            self._ctrl_anim.stop()
            self._ctrl_anim.setStartValue(self._ctrl_t)
            self._ctrl_anim.setEndValue(target)
            self._ctrl_anim.start()
        finally:
            self._ctrl_setting_up = False

    def _show_ctrl_if_hover(self):
        if self._hovered:
            self._animate_ctrl(1.0)

    def enterEvent(self, e):
        # 先把窗口加高（动画 300ms），胶囊再淡入 —— 胶囊一出现就已经在自己的
        # 预留行里，不会像旧版那样直接画在下一句歌词 / 进度条上
        self._hovered = True
        self._relayout()
        if self._size_anim.state() == QPropertyAnimation.Running:
            # 那一行还在长：此刻淡入，胶囊底部会被窗口边切掉一截（加高到 45%
            # 前位置不够）。等加高过半再淡入，视觉上是「先让位、再出现」。
            QTimer.singleShot(150, self._show_ctrl_if_hover)
        else:
            self._animate_ctrl(1.0)

    def leaveEvent(self, e):
        # 不在这里淡出。分层窗口按「像素 alpha」命中：鼠标从内容移向胶囊要跨过
        # 中间的透明间隙（内容下缘到胶囊之间的 6px、边距等），OS 会判定光标
        # 「已离开窗口」并发 leave —— 但光标明明还悬在悬浮层上。若立刻淡出，
        # 就会进入 进入→加高→离开→收回→再进入 的循环（悬停乱跳的另一半根因）。
        # 淡出改由 _on_frame 轮询全局光标位置触发：真出了窗口矩形才收。
        pass

    def showEvent(self, e):
        super().showEvent(e)
        t = getattr(self, "_timer", None)
        if t is not None and not t.isActive():
            t.start()                    # 重新可见：恢复帧定时器（隐藏期间它是停的）
        self._last_frame_pos = -1e9      # 强制下一帧重绘一次
        self._clamp_into_screen()        # 期间显示器可能变了/配置里存着屏外坐标
        self.update()

    def _clamp_into_screen(self):
        """把窗口整个夹回所在屏幕的工作区（availableGeometry，去掉任务栏）。

        用户实测：自由摆放的窗口停在屏幕边缘外时，卡片被屏幕裁掉一块；悬停
        为控制条加高的那 48px 又朝屏幕外侧长，胶囊整行落到屏幕外"出不来"。
        任何尺寸变化 / 拖拽 / 显示 / 恢复配置后都调它，保证窗口永远完整可见。
        """
        scr = self.screen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        w, h = self.width(), self.height()
        nx = min(max(self.x(), avail.left()),
                 max(avail.left(), avail.right() - w + 1))
        ny = min(max(self.y(), avail.top()),
                 max(avail.top(), avail.bottom() - h + 1))
        if nx != self.x() or ny != self.y():
            self.move(nx, ny)

    def hideEvent(self, e):
        super().hideEvent(e)
        # 隐藏（托盘「隐藏歌词」）：整条帧定时器停掉，空转开销归零。
        # 旧实现里隐藏后仍按 33ms 跑 _on_frame，实测白烧 1.6% CPU。
        t = getattr(self, "_timer", None)
        if t is not None:
            t.stop()
        # 定时器停了，悬停轮询也就停了 —— 隐藏时把悬停态直接复位，
        # 否则再次显示会带着一块未淡出的旧胶囊
        self._ctrl_anim.stop()
        self._ctrl_t = 0.0
        self._hovered = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # 贴边预设要跟着新尺寸重新落位：悬停为控制条加高的那几十像素，必须朝
        # 屏幕内侧长，不能越过锚点往任务栏方向顶（free = 用户拖的，保持左上角不动）
        if getattr(self, "_restore_position_done", False) and self.pos_preset != POS_FREE:
            self.move(*self._preset_point(self.pos_preset))
        # 自由摆放贴着屏幕下缘时，悬停加高会把窗口底压出屏幕外 —— 每次尺寸
        # 变化都夹回工作区，控制条才不会"长到屏幕外面去"
        self._clamp_into_screen()

    # ---------------- 悬浮控制条（一键播放控制） ----------------

    CTRL_CELL = 34
    CTRL_N = 6          # 上一首 播放/暂停 下一首 屏保 锁定 设置
    CTRL_H = 36         # 胶囊高度（悬停时窗口底部为它预留 CTRL_H + 12 的一行）

    def _ctrl_reserve(self) -> int:
        """悬停时窗口底部额外预留的高度；非悬停为 0（内容几何完全不变）"""
        return (self.CTRL_H + 12) if self._hovered else 0

    def _ctrl_min_window_w(self) -> int:
        """悬停时窗口宽度下限：至少装得下整条胶囊（左右各留 4px）。

        胶囊宽 6*CTRL_CELL+8=212 不随字号缩放，而各主题的窗口最小宽都比它
        窄（原生浮字短句 + font_scale 0.7 时仅约 202px，ios 约 207px）——
        `_ctrl_rect` 右锚定 `width - m - 212` 会算出负的左边，胶囊左端
        （上一首按钮整格）被窗口裁掉。悬停加宽由 300ms 尺寸动画顺带完成，
        收回悬停后窗口照旧缩回窄尺寸，非悬停观感不变。"""
        return self.CTRL_N * self.CTRL_CELL + 8 + 2 * 4

    def _content_rect(self) -> QRectF:
        """内容卡片区域：glass/ios/spotify 的卡片、vinyl 的内容中线都从这里推导。

        这是「几何即真相」的单一来源 —— 绘制与回归测试读同一个矩形，
        悬停时底部让出的那条就是控制条的位置。

        尺寸取 `_relayout` 存下的 `_layout_size` 而不是从窗口尺寸反推：
        反推会把 300ms 的加高动画当成内容变化，卡片先塌陷一整行再弹回来。
        """
        m = self._margin()
        pw, ph = self._layout_size
        return QRectF(m, m, pw, ph)

    def _ctrl_rect(self) -> QRectF:
        """锚在「内容区下缘 + 6px」而不是窗口底边。

        悬停时窗口要往下长高 48px（300ms 动画）：若锚窗口底边，胶囊会跟着
        底边一路滑走，鼠标原指着的那个点在动画结束后变成透明像素 —— 而本窗口
        是逐像素命中的分层窗口（透明处直接穿透），于是 leave → 收回 → 再进入
        无限循环，表现就是用户看到的「悬停时乱跳」。锚到内容区下缘后，胶囊
        在屏幕上的位置从出现到消失一个像素都不动。
        """
        w = self.CTRL_N * self.CTRL_CELL + 8
        m = self._margin()
        top = self._content_rect().bottom() + 6.0
        # 右锚定可能算出负的左边（窗口比胶囊还窄的窄窗场景）：夹回窗口内，
        # 优先保证右侧贴边距、左侧至少 4px，两端都不许出窗被裁
        left = min(self.width() - m - w, self.width() - w - 4.0)
        left = max(left, 4.0)
        return QRectF(left, top, w, self.CTRL_H)

    def _ctrl_button_at(self, pos) -> int:
        r = self._ctrl_rect()
        if self._ctrl_t < 0.5 or not r.contains(QPointF(pos)):
            return -1
        idx = int((pos.x() - r.left() - 4) // self.CTRL_CELL)
        return idx if 0 <= idx < self.CTRL_N else -1

    def _cell_rect(self, i: int, r: QRectF) -> QRectF:
        return QRectF(r.left() + 4 + i * self.CTRL_CELL, r.top(),
                      self.CTRL_CELL, r.height())

    def _stroke(self, p: QPainter, path: QPainterPath, pen: QPen):
        """只描边，不填充。

        QPainter.drawPath() 会顺带用「当前画刷」填充路径 —— 如果前面某个绘制
        （例如进度条白色滑块）留下了未复位的有色画刷，本想画 1px 边框的
        drawPath 会把整块区域涂成实色。控制条变白块就是这么来的。这里统一
        在描边前强制 NoBrush，让所有描边调用都不受上游画笔状态影响。
        """
        p.save()
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawPath(path)
        p.restore()

    def _paint_controls(self, p: QPainter):
        r = self._ctrl_rect()
        p.save()
        p.setOpacity(p.opacity() * self._ctrl_t)
        bg = QPainterPath()
        bg.addRoundedRect(r, r.height() / 2, r.height() / 2)      # 胶囊形，比圆角矩形更现代
        # 胶囊底改成竖向渐变 + 上缘内高光：纯平色读起来像一块塑料，渐变的"上亮下暗"
        # 加上顶部那条细亮线，才像一块有厚度、有受光的玻璃。
        cg = QLinearGradient(0, r.top(), 0, r.bottom())
        cg.setColorAt(0.0, QColor(31, 34, 43, 226))
        cg.setColorAt(0.55, QColor(15, 16, 21, 218))
        cg.setColorAt(1.0, QColor(9, 10, 14, 228))
        p.fillPath(bg, QBrush(cg))
        self._stroke(p, bg, QPen(QColor(255, 255, 255, 38), 1))
        if r.height() > 16:
            # 顶部内高光：把内缩 1px 的同一胶囊描边裁到上半部，只剩一条上缘亮弧
            hi = QPainterPath()
            hi.addRoundedRect(r.adjusted(1, 1, -1, -1),
                              r.height() / 2 - 1, r.height() / 2 - 1)
            p.save()
            p.setClipRect(QRectF(r.left(), r.top(), r.width(), r.height() * 0.5))
            self._stroke(p, hi, QPen(QColor(255, 255, 255, 34), 1))
            p.restore()
        # 全部矢量绘制，不用符号字体
        white = QColor(255, 255, 255, 232)
        # 中间一格做成「填充主色圆 + 白色三角」，一眼能找到播放键
        cr = self._cell_rect(1, r)
        cc = cr.center()
        p.setPen(Qt.NoPen)
        p.setBrush(self.accent1)
        p.drawEllipse(cc, cr.height() * 0.36, cr.height() * 0.36)
        draw_media_glyph(p, "pause" if self.status == "PLAYING" else "play",
                         QRectF(cr.x() + 2, cr.y() + 2, cr.width() - 4, cr.height() - 4),
                         QColor(255, 255, 255, 246))
        for i, kind in ((0, "prev"), (2, "next")):
            draw_media_glyph(p, kind, self._cell_rect(i, r), white)
        draw_media_glyph(p, "saver", self._cell_rect(3, r),
                         QColor(255, 255, 255, 200))
        draw_lock_glyph(p, self._cell_rect(4, r), self.locked)
        draw_media_glyph(p, "gear", self._cell_rect(5, r), white)
        p.restore()

    # ---------------- 布局 ----------------

    def _title_text(self):
        return "%s · %s" % (self.song.get("title") or "未知歌曲",
                            self.song.get("artist") or "未知歌手")

    NO_LYRIC_HINT = "♫ 纯音乐或暂无歌词"   # 无歌词时的占位文案（布局与绘制必须同源）

    def _idle_current_text(self) -> str:
        """当前行空位时的回退文案，按情况区分：

        · 有歌词但还没唱到（前奏/间奏）→ 「♪ 歌名」。前奏期显示「纯音乐或暂无
          歌词」会让人以为第一句歌词丢了（用户反馈的"不显示第一行歌词"就是这个）。
        · 真没歌词 → 纯音乐占位。
        布局（_pill_size 估宽）与绘制必须同源，都走这里。
        """
        if self.lines:
            return "♪ " + self._title_text()
        return self.NO_LYRIC_HINT

    def _tr_text(self) -> str:
        # 当前行没内容（无歌词 / 歌词未加载）时不垫翻译
        if not self.show_trans or self.cur_idx < 0 or not self._current_text:
            return ""
        return self._trans_for(self.cur_idx)

    def _prelude_texts(self):
        """前奏/间奏期（还没唱到第一句）的 (当前行, 下一行) 文案。

        第一句直接放进当前行、以「未唱态」显示（逐字进度按 pos 实时计算，此刻
        全暗，唱到自然点亮），下一行挂第二句。旧设计把第一句压在"下一行"小字里、
        当前行显示歌名/纯音乐占位 —— 用户会当成"第一行歌词不显示"（纯音乐占位
        更是误导，明明有歌词）。第一句入场动画改在歌词加载完成时播，唱到时不再
        重播（行已经就在位置上）。
        """
        nxt = self.lines[1][1] if len(self.lines) > 1 else ""
        return self.lines[0][1], nxt

    def _time_text(self) -> str:
        if not self.show_time or self.duration <= 0:
            return ""
        return "%s / %s" % (self._fmt_time(self._current_pos()), self._fmt_time(self.duration))

    def _pill_size(self):
        m = self._margin()
        if not self.song:
            if self.style_mode == "native":
                fm_c = QFontMetrics(self._font_cur(self._px(30)))
                fm_n = QFontMetrics(self._font_reg(self._px(15)))
                w = max(fm_c.horizontalAdvance("等待播放…"),
                        fm_n.horizontalAdvance("在 QQ音乐 / 网易云 播放歌曲即可显示歌词"))
                return (w + 2 * m, fm_c.height() + 5 + fm_n.height() + 2 * m)
            if self.style_mode == "vinyl":
                disc = self._px(VINYL_DISC)
                fm_c = QFontMetrics(self._font_cur(self._px(20)))
                w = 2 * m + disc + self._px(VINYL_GAP) + fm_c.horizontalAdvance("等待播放…")
                return (w, 2 * m + disc)
            if self.style_mode == "ios":
                return self._px(340), self._px(96)
            if self.style_mode == "spotify":
                return self._px(320), self._px(80)
            return self._px(330), self._px(78)
        if self.style_mode == "native":
            fm_c = QFontMetrics(self._font_cur(self._px(32)))
            fm_n = QFontMetrics(self._font_reg(self._px(16)))
            cov_gap = (self._px(COVER_N) + self._px(GAP_N)) if self.show_cover else 0
            avail = self._px(940) - 2 * m - cov_gap
            cur = self._current_text or ("♪ " + self._title_text())
            nxt = self._next_text or ""
            tr = self._tr_text()
            w = min(fm_c.horizontalAdvance(cur), avail)
            rows = fm_c.height()
            if tr:
                w = max(w, min(fm_n.horizontalAdvance(tr), avail))
                rows += 4 + fm_n.height()
            if nxt:
                w = max(w, min(fm_n.horizontalAdvance(nxt), avail))
                rows += 4 + fm_n.height()
            block = max(w, self._px(220))
            return (2 * m + cov_gap + block, rows + 2 * m)
        if self.style_mode == "ios":
            f_t, f_c, f_n = (self._font_med(self._px(12)), self._font_cur(self._px(26)),
                             self._font_reg(self._px(14)))
            fm_t, fm_c, fm_n = QFontMetrics(f_t), QFontMetrics(f_c), QFontMetrics(f_n)
            pad, cov, gap = self._px(18), self._px(IOS_COVER), self._px(IOS_GAP)
            cov_w = (cov + gap) if self.show_cover else 0
            avail = self._px(760) - pad * 2 - cov_w
            cur = self._current_text or self._title_text()
            nxt = self._next_text or ""
            tr = self._tr_text()
            w_text = max(min(fm_c.horizontalAdvance(cur), avail),
                         min(fm_n.horizontalAdvance(nxt), avail) if nxt else 0,
                         min(fm_n.horizontalAdvance(tr), avail) if tr else 0,
                         self._px(260))
            w = pad * 2 + cov_w + w_text
            h = 16 + fm_t.height() + 8 + fm_c.height()
            if tr:
                h += 4 + fm_n.height()
            if nxt:
                h += 4 + fm_n.height()
            h += 30
            return w, h
        if self.style_mode == "vinyl":
            disc = self._px(VINYL_DISC)
            f_c, f_n = self._font_cur(self._px(24)), self._font_reg(self._px(14))
            fm_c, fm_n = QFontMetrics(f_c), QFontMetrics(f_n)
            cur = self._current_text or self._title_text()
            nxt = self._next_text or ""
            tr = self._tr_text()
            avail = self._px(560)
            w_text = max(min(fm_c.horizontalAdvance(cur), avail),
                         min(fm_n.horizontalAdvance(nxt), avail) if nxt else 0,
                         min(fm_n.horizontalAdvance(tr), avail) if tr else 0,
                         self._px(220))
            rows = fm_c.height()
            if tr:
                rows += 4 + fm_n.height()
            if nxt:
                rows += 4 + fm_n.height()
            return (2 * m + disc + self._px(VINYL_GAP) + w_text,
                    2 * m + max(disc, rows + self._px(28)))
        if self.style_mode == "spotify":
            f_t, f_c, f_n = (self._font_med(self._px(11)), self._font_cur(self._px(22)),
                             self._font_reg(self._px(13)))
            fm_t, fm_c, fm_n = QFontMetrics(f_t), QFontMetrics(f_c), QFontMetrics(f_n)
            pad_l, pad_r = self._px(SP_PAD_L), self._px(SP_PAD_R)
            cov_gap = (self._px(SP_COVER) + self._px(SP_GAP)) if self.show_cover else 0
            avail = self._px(720) - pad_l - pad_r - cov_gap
            cur = self._current_text or self._title_text()
            nxt = self._next_text or ""
            tr = self._tr_text()
            w_text = max(min(fm_c.horizontalAdvance(cur), avail),
                         min(fm_n.horizontalAdvance(nxt), avail) if nxt else 0,
                         min(fm_n.horizontalAdvance(tr), avail) if tr else 0,
                         self._px(240))
            w = pad_l + cov_gap + w_text + pad_r
            h = 12 + fm_t.height() + 6 + fm_c.height()
            if tr:
                h += 4 + fm_n.height()
            if nxt:
                h += 4 + fm_n.height()
            h += 26
            return max(self._px(320), min(w, self._px(760))), h
        # glass：高度按字体度量推导，随字号缩放
        f_med, f_cur, f_next = (self._font_med(self._px(12)), self._font_cur(self._px(23)),
                                self._font_reg(self._px(13)))
        fm_t, fm_c, fm_n = QFontMetrics(f_med), QFontMetrics(f_cur), QFontMetrics(f_next)
        pad_l, pad_r = self._px(PAD_L), self._px(PAD_R)
        cov_gap = (self._px(COVER) + self._px(GAP)) if self.show_cover else 0
        avail = self._px(800) - pad_l - pad_r - cov_gap
        cur = self._current_text or self._idle_current_text()   # 与绘制里的回退文案同源，宽度才不会估窄
        nxt = self._next_text or ""
        tr = self._tr_text()
        title = self._title_text()
        w_text = max(
            min(fm_t.horizontalAdvance(title), avail),
            min(fm_c.horizontalAdvance(cur), avail),
            min(fm_n.horizontalAdvance(nxt), avail) if nxt else 0,
            min(fm_n.horizontalAdvance(tr), avail) if tr else 0,
            self._px(240),
        )
        w = pad_l + w_text + pad_r + cov_gap
        h = 12 + fm_t.height() + 8 + fm_c.height()
        if tr:
            h += 4 + fm_n.height()
        if nxt:
            h += 4 + fm_n.height()
        h += 30
        return max(self._px(320), min(w, self._px(830))), h

    def _relayout(self):
        pw, ph = self._pill_size()
        # 内容几何在这里定死一份：绘制（含黑胶中线、黑胶封面居中、控制条落点）
        # 一律读它，而不是拿「当前窗口高」去反推 —— 否则悬停加高的 300ms 动画里，
        # 窗口还是旧高度、预留行却已生效，卡片会先被压掉一整行再弹回来。
        self._layout_size = (pw, ph)
        w, h = (pw + 2 * self._margin(),
                ph + 2 * self._margin() + self._ctrl_reserve())
        if self._hovered:
            w = max(w, self._ctrl_min_window_w())   # 窄窗也要装得下整条胶囊
        if abs(self.width() - w) > 2 or abs(self.height() - h) > 2:
            self._size_anim.stop()
            self._size_anim.setStartValue(self.size())
            self._size_anim.setEndValue(QSize(w, h))
            self._size_anim.start()

    def _relayout_instant(self):
        """立刻落到目标尺寸（无事件循环的离屏渲染 / 预览脚本用）。

        与 _relayout 共用同一份几何真相，避免预览里另算一遍尺寸而与真实观感分叉。
        """
        pw, ph = self._pill_size()
        self._layout_size = (pw, ph)
        m = self._margin()
        self._size_anim.stop()
        w = max(pw + 2 * m, self._ctrl_min_window_w()) if self._hovered \
            else pw + 2 * m
        self.resize(int(w), int(ph + 2 * m + self._ctrl_reserve()))

    # ---------------- 绘制 ----------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.TextAntialiasing)

        if self.status != "PLAYING" and not self.pause_fade:
            p.setOpacity(0.88)  # 未开自动淡出时，暂停仍在画面层压暗

        try:
            if self.style_mode == "native":
                self._paint_native(p)
            elif self.style_mode == "vinyl":
                self._paint_vinyl(p)
            elif self.style_mode == "ios":
                self._paint_ios(p)
            elif self.style_mode == "spotify":
                self._paint_spotify(p)
            else:
                self._paint_glass(p)
        except Exception:
            # 绘制异常只降级当帧，不拖崩整个程序
            log("paint error:\n" + traceback.format_exc())

        if self.edge_fade:
            self._paint_edge_fade(p)
        if self._ctrl_t > 0.01:
            self._paint_controls(p)

    def _paint_edge_fade(self, p: QPainter):
        """边缘虚化：用 DestinationIn 双向渐变把窗口四边羽化掉"""
        w, h = self.width(), self.height()
        f = min(self.edge_fade_px, max(0, (min(w, h) - 1) // 2))
        if f <= 1:
            return
        p.save()
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        g = QLinearGradient(0, 0, 0, h)
        a = f / h
        g.setColorAt(0.0, QColor(0, 0, 0, 0))
        g.setColorAt(a, QColor(0, 0, 0, 255))
        g.setColorAt(1.0 - a, QColor(0, 0, 0, 255))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, QBrush(g))
        g2 = QLinearGradient(0, 0, w, 0)
        b = f / w
        g2.setColorAt(0.0, QColor(0, 0, 0, 0))
        g2.setColorAt(b, QColor(0, 0, 0, 255))
        g2.setColorAt(1.0 - b, QColor(0, 0, 0, 255))
        g2.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, QBrush(g2))
        p.restore()

    def _paint_glow(self, p: QPainter, card: QRectF):
        """氛围光晕：卡片外圈铺一层封面主色径向渐变，播放时轻微呼吸

        注：渐变半径 = max(卡片宽, 高) × 0.6，对「宽卡片」来说其外接矩形本就覆盖
        整个窗口（四角也在渐变末端有极淡余量），所以这里不做收窄——省不到像素，
        收窄反而会把四角的余晖切出硬边。
        """
        if not self.glow or not self.song:
            return
        c = card.center()
        r = max(card.width(), card.height()) * 0.60
        pulse = 0.80 + 0.20 * (0.5 + 0.5 * math.sin(self._glow_ph))
        a = int(104 * pulse)
        grad = QRadialGradient(c, r)
        grad.setColorAt(0.00, QColor(self.accent1.red(), self.accent1.green(),
                                     self.accent1.blue(), a))
        grad.setColorAt(0.55, QColor(self.accent2.red(), self.accent2.green(),
                                     self.accent2.blue(), int(a * 0.45)))
        grad.setColorAt(1.00, QColor(self.accent2.red(), self.accent2.green(),
                                     self.accent2.blue(), 0))
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(0, 0, self.width(), self.height())
        p.restore()

    def _paint_native(self, p: QPainter):
        m = self._margin()
        if not self.song:
            fm_c = QFontMetrics(self._font_cur(self._px(30)))
            fm_n = QFontMetrics(self._font_reg(self._px(15)))
            t1, t2 = "等待播放…", "在 QQ音乐 / 网易云 播放歌曲即可显示歌词"
            p.setOpacity(p.opacity() * (0.55 + 0.45 * abs(time.time() % 2 - 1)))
            self._draw_plain(p, t1, (self.width() - fm_c.horizontalAdvance(t1)) / 2,
                             m + fm_c.ascent(), self._font_cur(self._px(30)), fm_c,
                             HALO_BARE, 238)
            self._draw_plain(p, t2, (self.width() - fm_n.horizontalAdvance(t2)) / 2,
                             m + fm_c.height() + 5 + fm_n.ascent(),
                             self._font_reg(self._px(15)), fm_n, 2.4, 176)
            return

        x = m
        if self.show_cover:
            cov = self._px(COVER_N)
            c = self._content_rect()    # 封面在内容区里居中（悬停加高时不跟歌词错位）
            self._paint_cover(p, x, c.top() + (c.height() - cov) / 2, cov, 10)
            x += cov + self._px(GAP_N)

        avail = self.width() - x - m
        f_next = self._font_reg(self._px(16))
        fm_n = QFontMetrics(f_next)
        raw_cur = self._current_text or ("♪ " + self._title_text())
        f_cur, fm_c = self._fit_font(self._font_cur, self._px(32), raw_cur, avail)
        cur = fm_c.elidedText(raw_cur, Qt.ElideRight, max(60, avail))

        p.save()
        self._apply_line_anim(p)
        if self.cur_idx >= 0 and self.lines and self._current_text:
            self._draw_karaoke(p, cur, x, m + fm_c.ascent(), f_cur, fm_c,
                               self.cur_idx, halo_w=HALO_BARE, dim_alpha=DIM_BARE, rise=5.0)
        else:
            self._draw_plain(p, cur, x, m + fm_c.ascent(), f_cur, fm_c, HALO_BARE, 238)
        y_row = m + fm_c.height() + 4 + fm_n.ascent()
        tr = self._tr_text()
        if tr:
            self._draw_trans(p, fm_n.elidedText(tr, Qt.ElideRight, max(60, avail)),
                             x, y_row, f_next, fm_n)
            y_row += fm_n.height() + 2
        if self._next_text:
            nxt = fm_n.elidedText(self._next_text, Qt.ElideRight, max(60, avail))
            # 无卡片底的样式，下一句在浅色壁纸上要更实才读得清（v2.4.18: 176→204）
            self._draw_plain(p, nxt, x, y_row, f_next, fm_n, 2.6, 204)
        p.restore()

    def _paint_glass(self, p: QPainter):
        m = self._margin()
        pill = self._content_rect()     # 悬停时底部让出一条给控制条
        self._paint_glow(p, pill)
        path = QPainterPath()
        path.addRoundedRect(pill, PILL_RADIUS, PILL_RADIUS)

        top = QColor(self.bg_color)
        top.setAlpha(198)
        bottom = QColor(self.bg_color)
        bottom.setAlpha(226)
        bg_grad = QLinearGradient(pill.topLeft(), pill.bottomLeft())
        bg_grad.setColorAt(0, top)
        bg_grad.setColorAt(1, bottom)
        p.fillPath(path, QBrush(bg_grad))
        self._stroke(p, path, QPen(QColor(self.accent1.red(), self.accent1.green(),
                                          self.accent1.blue(), 55), 1))

        if not self.song:
            p.setOpacity(1.0)
            self._paint_waiting(p, pill)
            return

        pad_l, pad_r = self._px(PAD_L), self._px(PAD_R)
        cov = self._px(COVER)
        f_med, f_cur, f_next = (self._font_med(self._px(12)), self._font_cur(self._px(23)),
                                self._font_reg(self._px(13)))
        fm_t, fm_c, fm_n = QFontMetrics(f_med), QFontMetrics(f_cur), QFontMetrics(f_next)

        x = m + pad_l
        if self.show_cover:
            self._paint_cover(p, x, pill.y() + (pill.height() - cov) / 2 - 4, cov, 13)
            x += cov + self._px(GAP)

        avail = pill.right() - pad_r - x

        # 标题行 + 均衡器（基线按字体度量推导，随字号缩放）
        y_title = pill.y() + 12 + fm_t.ascent()
        y_cur = y_title + fm_t.descent() + 8 + fm_c.ascent()
        tr = self._tr_text()
        y_row = y_cur + fm_c.descent() + 4 + fm_n.ascent()
        y_tr = y_row if tr else 0.0
        if tr:
            y_row += fm_n.height() + 2
        y_next = y_row

        title = fm_t.elidedText(self._title_text(), Qt.ElideRight, max(60, avail - 40))
        p.setFont(f_med)
        # 标题行不随切行动画闪：旧版 alpha 绑了 _line_t，每切一次行标题就跟着闪一下
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(QPointF(x, y_title), title)
        self._paint_equalizer(p, x + fm_t.horizontalAdvance(title) + 10,
                              y_title - 9, self.status == "PLAYING")

        p.save()
        self._apply_line_anim(p)
        raw_cur = self._current_text or self._idle_current_text()
        f_cur2, fm_c2 = self._fit_font(self._font_cur, self._px(23), raw_cur, avail)
        cur = fm_c2.elidedText(raw_cur, Qt.ElideRight, max(60, avail))
        # 只有当前行真的有歌词才走卡拉OK —— 前奏期 cur_idx 已指向第 0 行而
        # _current_text 还是空，旧版会把进度填色画到占位/歌名回退文本上
        if self.cur_idx >= 0 and self.lines and self._current_text:
            self._draw_karaoke(p, cur, x, y_cur, f_cur2, fm_c2,
                               self.cur_idx, halo_w=HALO_CARD, dim_alpha=DIM_CARD, rise=4.0)
        else:
            self._draw_plain(p, cur, x, y_cur, f_cur2, fm_c2, HALO_CARD, 232)
        if tr:
            txt = fm_n.elidedText(tr, Qt.ElideRight, max(60, avail))
            self._draw_trans(p, txt, x, y_tr, f_next, fm_n)
        if self._next_text:
            nxt = fm_n.elidedText(self._next_text, Qt.ElideRight, max(60, avail))
            self._draw_plain(p, nxt, x, y_next, f_next, fm_n, 2.0, 138)
        p.restore()

        # 底部进度条 + 时间（统一走 _draw_progress，与 iOS / Spotify 同一套观感）
        if self.duration > 0:
            frac = max(0.0, min(1.0, self._current_pos() / self.duration))
            bar_y = pill.bottom() - 11
            bar_w = self._paint_time(p, pill.right() - pad_r, bar_y, frac)
            self._draw_progress(p, x, bar_y, max(40.0, bar_w - x), frac, 3.0, knob=True)

    def _draw_progress(self, p: QPainter, x: float, y: float, w: float,
                       frac: float, h: float = 3.0, knob: bool = False,
                       c1: QColor = None, c2: QColor = None, dark_track: bool = False):
        """细进度条（可选圆点滑块），配色默认取封面主色渐变

        dark_track：无卡片底的样式（黑胶）用。单用白色轨道会在浅色壁纸上消失，
        单用黑色轨道会在深色壁纸上消失，所以这里先铺一圈略大的深色「垫底」再叠
        浅色轨道——两种壁纸上都看得见。
        """
        # 整个函数用 save/restore 包住：滑块最后会 setBrush(纯白)，若不还原，
        # 后续任何 drawPath() 描边都会被这把白刷子填满（控制条整条变白块的根因）。
        p.save()
        track = QRectF(x, y, w, h)
        p.setPen(Qt.NoPen)
        if dark_track:
            p.setBrush(QColor(0, 0, 0, 96))
            p.drawRoundedRect(track.adjusted(-1.5, -1.5, 1.5, 1.5),
                              h / 2 + 1.5, h / 2 + 1.5)
            p.setBrush(QColor(255, 255, 255, 92))
        else:
            p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(track, h / 2, h / 2)
        if frac > 0.003:
            grad = QLinearGradient(track.topLeft(), track.topRight())
            grad.setColorAt(0, c1 or self.accent1)
            grad.setColorAt(1, c2 or self.accent2)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(track.left(), track.y(),
                                     max(h, track.width() * frac), h), h / 2, h / 2)
        if knob:
            # 滑块加一圈深色细边，浅色壁纸/浅色轨道上也有边界（无卡片样式必需）
            kr = h * 1.15
            if dark_track:
                p.setBrush(QColor(0, 0, 0, 110))
                p.drawEllipse(QPointF(x + w * frac, y + h / 2), kr + 1.2, kr + 1.2)
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(x + w * frac, y + h / 2), kr, kr)
        p.restore()

    # ---------------- iOS 音乐卡片 ----------------

    def _paint_ios(self, p: QPainter):
        m = self._margin()
        card = self._content_rect()     # 悬停时底部让出一条给控制条
        self._paint_glow(p, card)
        path = QPainterPath()
        path.addRoundedRect(card, IOS_RADIUS, IOS_RADIUS)
        bg = QLinearGradient(card.topLeft(), card.bottomLeft())
        bg.setColorAt(0, QColor(34, 34, 40, 214))
        bg.setColorAt(1, QColor(16, 16, 20, 232))
        p.fillPath(path, QBrush(bg))
        self._stroke(p, path, QPen(QColor(255, 255, 255, 30), 1))

        if not self.song:
            p.setFont(self._font_cur(self._px(18)))
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(card, Qt.AlignCenter, "等待播放…")
            return

        f_t, f_c, f_n = (self._font_med(self._px(12)), self._font_cur(self._px(26)),
                         self._font_reg(self._px(14)))
        fm_t, fm_c, fm_n = QFontMetrics(f_t), QFontMetrics(f_c), QFontMetrics(f_n)
        pad, cov, gap = self._px(18), self._px(IOS_COVER), self._px(IOS_GAP)

        x = m + pad
        if self.show_cover:
            self._paint_cover(p, x, card.y() + pad, cov, 16)
            x += cov + gap
        avail = card.right() - pad - x

        y_t = card.y() + pad + fm_t.ascent()
        y_c = y_t + fm_t.descent() + 8 + fm_c.ascent()
        tr = self._tr_text()
        y_row = y_c + fm_c.descent() + 6 + fm_n.ascent()
        y_tr = y_row if tr else 0.0
        if tr:
            y_row += fm_n.height() + 2
        y_n = y_row

        # 顶部小标题（iOS 式大写灰色小字）
        title = fm_t.elidedText(self._title_text(), Qt.ElideRight, max(60, avail))
        p.setFont(f_t)
        p.setPen(QColor(235, 235, 245, 100))
        p.drawText(QPointF(x, y_t), title)

        p.save()
        self._apply_line_anim(p)
        raw_cur = self._current_text or self._title_text()
        f_c2, fm_c2 = self._fit_font(self._font_cur, self._px(26), raw_cur, avail)
        cur = fm_c2.elidedText(raw_cur, Qt.ElideRight, max(60, avail))
        if self.cur_idx >= 0 and self.lines and self._current_text:
            self._draw_karaoke(p, cur, x, y_c, f_c2, fm_c2, self.cur_idx,
                               halo_w=0, dim_alpha=DIM_CARD, rise=4.0, halo_on=False)
        else:
            self._draw_plain(p, cur, x, y_c, f_c2, fm_c2, 0, 245, halo_on=False)
        if tr:
            self._draw_trans(p, fm_n.elidedText(tr, Qt.ElideRight, max(60, avail)),
                             x, y_tr, f_n, fm_n)
        if self._next_text:
            nxt = fm_n.elidedText(self._next_text, Qt.ElideRight, max(60, avail))
            p.setFont(f_n)
            p.setPen(QColor(235, 235, 245, 82))
            p.drawText(QPointF(x, y_n), nxt)
        p.restore()

        # 细进度条 + 圆点滑块 + 时间（iOS Now Playing 式）
        if self.duration > 0:
            frac = max(0.0, min(1.0, self._current_pos() / self.duration))
            y_bar = card.bottom() - 22
            bar_right = self._paint_time(p, card.right() - pad, y_bar - 2, frac)
            self._draw_progress(p, x, y_bar, max(40.0, bar_right - x), frac, 4.0, knob=True)

    # ---------------- 黑胶唱片 ----------------

    def _paint_vinyl(self, p: QPainter):
        m = self._margin()
        disc = self._px(VINYL_DISC)
        content = self._content_rect()  # 悬停时底部让出一条给控制条
        cx, cy = m + disc / 2, content.top() + content.height() / 2
        self._paint_glow(p, QRectF(cx - disc / 2, cy - disc / 2, disc, disc))
        self._draw_vinyl(p, cx, cy, disc / 2)

        if not self.song:
            f = self._font_cur(self._px(20))
            fm = QFontMetrics(f)
            p.setOpacity(p.opacity() * (0.55 + 0.45 * abs(time.time() % 2 - 1)))
            self._draw_plain(p, "等待播放…", m + disc + self._px(VINYL_GAP),
                             cy + fm.ascent() / 2 - 2, f, fm, HALO_BARE, 224)
            return

        f_c, f_n = self._font_cur(self._px(24)), self._font_reg(self._px(14))
        fm_c, fm_n = QFontMetrics(f_c), QFontMetrics(f_n)
        x = m + disc + self._px(VINYL_GAP)
        avail = self.width() - x - m
        raw_cur = self._current_text or ("♪ " + self._title_text())
        f_c, fm_c = self._fit_font(self._font_cur, self._px(24), raw_cur, avail)
        cur = fm_c.elidedText(raw_cur, Qt.ElideRight, max(60, avail))
        tr = self._tr_text()
        block_h = fm_c.height()
        if tr:
            block_h += 4 + fm_n.height()
        if self._next_text:
            block_h += 4 + fm_n.height()
        top = cy - block_h / 2

        p.save()
        self._apply_line_anim(p)
        if self.cur_idx >= 0 and self.lines and self._current_text:
            self._draw_karaoke(p, cur, x, top + fm_c.ascent(), f_c, fm_c,
                               self.cur_idx, halo_w=HALO_BARE, dim_alpha=DIM_BARE, rise=4.0)
        else:
            self._draw_plain(p, cur, x, top + fm_c.ascent(), f_c, fm_c, HALO_BARE, 238)
        y_row = top + fm_c.height() + 4 + fm_n.ascent()
        if tr:
            self._draw_trans(p, fm_n.elidedText(tr, Qt.ElideRight, max(60, avail)),
                             x, y_row, f_n, fm_n)
            y_row += fm_n.height() + 2
        if self._next_text:
            nxt = fm_n.elidedText(self._next_text, Qt.ElideRight, max(60, avail))
            # 无卡片底的样式，下一句在浅色壁纸上要更实才读得清（v2.4.18: 172→200）
            self._draw_plain(p, nxt, x, y_row, f_n, fm_n, 2.6, 200)
        p.restore()

        # 歌词块下方的细进度线 + 时间（无卡片底，用深色轨道 + 描边文字）
        if self.duration > 0:
            frac = max(0.0, min(1.0, self._current_pos() / self.duration))
            y_bar = top + block_h + 9
            bar_right = self._paint_time(p, min(x + self._px(440), self.width() - m),
                                         y_bar - 1, frac, halo=True)
            self._draw_progress(p, x, y_bar, max(60.0, bar_right - x), frac, 2.8,
                                knob=True, dark_track=True)

    def _draw_vinyl(self, p: QPainter, cx: float, cy: float, r: float):
        p.save()
        p.translate(cx, cy)
        # 盘体
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(14, 14, 17))
        p.drawEllipse(QPointF(0, 0), r, r)
        # 唱纹（同心细环）
        p.setPen(QPen(QColor(255, 255, 255, 13), 1))
        p.setBrush(Qt.NoBrush)
        for i in range(1, 7):
            rr = r * (0.50 + 0.08 * i)
            p.drawEllipse(QPointF(0, 0), rr, rr)
        # 固定光泽带（不随盘转，模拟环境反光）
        p.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(0, 0), r - 1, r - 1)
        p.setClipPath(clip)
        sheen = QLinearGradient(-r, -r, r, r)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.42, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.5, QColor(255, 255, 255, 34))
        sheen.setColorAt(0.58, QColor(255, 255, 255, 0))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sheen))
        p.drawEllipse(QPointF(0, 0), r, r)
        p.restore()
        # 中心标签 = 专辑封面，随盘旋转
        p.save()
        p.rotate(self._vinyl_ang)
        lr = r * 0.36
        label = QPainterPath()
        label.addEllipse(QPointF(0, 0), lr, lr)
        p.setClipPath(label)
        if self.cover_pix and not self.cover_pix.isNull():
            want = int(lr * 4)
            if self._vinyl_pix is None or self._vinyl_pix_size != want:
                self._vinyl_pix = self.cover_pix.scaled(
                    want, want, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self._vinyl_pix_size = want
            p.drawPixmap(QPointF(-lr, -lr), self._vinyl_pix)
        else:
            g = QLinearGradient(-lr, -lr, lr, lr)
            g.setColorAt(0, self.accent1)
            g.setColorAt(1, self.accent2)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(0, 0), lr, lr)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 10, 12))
        p.drawEllipse(QPointF(0, 0), r * 0.035, r * 0.035)   # 中孔
        p.restore()
        # 标签环 + 外缘高光
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), r * 0.36, r * 0.36)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.2))
        p.drawEllipse(QPointF(0, 0), r - 0.8, r - 0.8)
        p.restore()

    # ---------------- Spotify 声波卡片 ----------------

    def _paint_spotify(self, p: QPainter):
        m = self._margin()
        card = self._content_rect()     # 悬停时底部让出一条给控制条
        self._paint_glow(p, card)
        path = QPainterPath()
        path.addRoundedRect(card, SP_RADIUS, SP_RADIUS)
        bg = QLinearGradient(card.topLeft(), card.bottomLeft())
        bg.setColorAt(0, QColor(30, 30, 30, 234))
        bg.setColorAt(1, QColor(12, 12, 12, 240))
        p.fillPath(path, QBrush(bg))
        self._stroke(p, path, QPen(QColor(255, 255, 255, 22), 1))

        if not self.song:
            p.setFont(self._font_cur(self._px(18)))
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(card, Qt.AlignCenter, "等待播放…")
            return

        f_t, f_c, f_n = (self._font_med(self._px(11)), self._font_cur(self._px(22)),
                         self._font_reg(self._px(13)))
        fm_t, fm_c, fm_n = QFontMetrics(f_t), QFontMetrics(f_c), QFontMetrics(f_n)
        pad_l, pad_r = self._px(SP_PAD_L), self._px(SP_PAD_R)
        cov, gap = self._px(SP_COVER), self._px(SP_GAP)

        x = m + pad_l
        if self.show_cover:
            self._paint_cover(p, x, card.y() + (card.height() - cov) / 2 - 3, cov, 8)
            x += cov + gap
        avail = card.right() - pad_r - x

        y_t = card.y() + 12 + fm_t.ascent()
        y_c = y_t + fm_t.descent() + 6 + fm_c.ascent()
        tr = self._tr_text()
        y_row = y_c + fm_c.descent() + 4 + fm_n.ascent()
        y_tr = y_row if tr else 0.0
        if tr:
            y_row += fm_n.height() + 2
        y_n = y_row

        # 顶部：绿点 + 正在播放 + 标题（Spotify 上下文行式样）
        dot_y = y_t - fm_t.ascent() + fm_t.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(SPOTIFY_GREEN)
        p.drawEllipse(QPointF(x + 3.2, dot_y), 3.2, 3.2)
        p.setFont(f_t)
        p.setPen(QColor(255, 255, 255, 130))
        top_text = fm_t.elidedText("正在播放  ·  " + self._title_text(),
                                   Qt.ElideRight, max(60, avail - 16))
        p.drawText(QPointF(x + 13, y_t), top_text)

        p.save()
        self._apply_line_anim(p)
        raw_cur = self._current_text or self._title_text()
        f_c2, fm_c2 = self._fit_font(self._font_cur, self._px(22), raw_cur, avail)
        cur = fm_c2.elidedText(raw_cur, Qt.ElideRight, max(60, avail))
        if self.cur_idx >= 0 and self.lines and self._current_text:
            self._draw_karaoke(p, cur, x, y_c, f_c2, fm_c2, self.cur_idx,
                               halo_w=0, dim_alpha=DIM_CARD, rise=4.0, halo_on=False)
        else:
            self._draw_plain(p, cur, x, y_c, f_c2, fm_c2, 0, 245, halo_on=False)
        if tr:
            self._draw_trans(p, fm_n.elidedText(tr, Qt.ElideRight, max(60, avail)),
                             x, y_tr, f_n, fm_n)
        if self._next_text:
            nxt = fm_n.elidedText(self._next_text, Qt.ElideRight, max(60, avail))
            p.setFont(f_n)
            p.setPen(QColor(255, 255, 255, 76))
            p.drawText(QPointF(x, y_n), nxt)
        p.restore()

        # 底部细进度条 + 时间（封面主色；绿色小点已并入顶部）
        if self.duration > 0:
            frac = max(0.0, min(1.0, self._current_pos() / self.duration))
            y_bar = card.bottom() - 16
            bar_right = self._paint_time(p, card.right() - pad_r, y_bar - 2, frac)
            self._draw_progress(p, x, y_bar, max(40.0, bar_right - x), frac, 3.0, knob=True)

    def _draw_karaoke(self, p: QPainter, text: str, x: float, y: float, font: QFont,
                      fm: QFontMetrics, idx: int, halo_w: float,
                      dim_alpha: int = 100, rise: float = 5.0, halo_on: bool = True):
        """逐字卡拉OK：字符按各自时间轴上浮 + 由暗变亮（封面主色渐变）"""
        if not text:
            return
        pos = self._lyric_pos()
        spans = self._char_spans(idx, text)
        line_w = max(1.0, fm.horizontalAdvance(text))
        halo = self._halo_pens(halo_w)
        rise = self._px(rise)
        style = self.anim_style
        f = _smoothstep(self._line_t)                 # 整行入场进度（切行时 0 → 1）
        cxp = x + line_w / 2.0                        # 整行中线
        fan_r = max(line_w * FAN_R_FACTOR, FAN_R_MIN)
        wave_amp = self._px(WAVE_AMP)
        for k, ch in enumerate(text):
            if ch in (" ", "　"):
                continue
            sp = spans[k] if k < len(spans) else None
            if sp is None:
                prog = 1.0
            else:
                t0, t1 = sp
                prog = 1.0 if t1 <= t0 else min(1.0, max(0.0, (pos - t0) / (t1 - t0)))
            e = 1.0 - (1.0 - prog) ** 3
            cx = x + fm.horizontalAdvance(text[:k])
            g = self._accent_at((cx + fm.horizontalAdvance(ch) / 2 - x) / line_w)

            # ---- 逐字变换：不同动画样式给不同位移/旋转/缩放 ----
            dxc = dyc = deg = 0.0
            scal = 1.0
            filled_e = e
            if style == "rise" or style not in ("pop", "wave", "fan", "typer"):
                dyc = rise * (1.0 - e)                 # 未唱到的字略低，唱到即上浮归位
            elif style == "pop":
                sv = 1.0 + 0.46 * (1.0 - e)
                scal = min(1.9, sv)
                dyc = -self._px(5.0) * (1.0 - e)       # 从上方落下 + 弹性放大
            elif style == "wave":
                dyc = -wave_amp * math.sin(k * 0.60 - pos * 2.8)
            elif style == "fan":
                d = (cx + fm.horizontalAdvance(ch) / 2.0) - cxp
                phi = d / fan_r                        # 目标弧角（整扇展开时）
                tx = cxp + fan_r * math.sin(phi)
                ty = y + fan_r * (1.0 - math.cos(phi))
                dxc = f * (tx - cx - fm.horizontalAdvance(ch) / 2.0)
                dyc = f * (ty - y)
                deg = math.degrees(f * phi)
            elif style == "typer":
                filled_e = 1.0 if prog > 0 else 0.0     # 硬切入字，不渐变

            # 正在唱的这一个字：沿字宽铺一条横向渐变，把"唱过/未唱"的边界铺软。
            # 原来整字一个平色，视线扫过去是"一格一格跳"；改成渐变后相邻字的渐变
            # 互相搭接，整行读起来是一道连续推进的波前（typer 走硬切，保持打字机感）。
            # 方向不能搞反：波前从字左往字右推进，所以**左端是已唱（t 大）、右端是未唱（t 小）**。
            if KARAOKE_SOFT_EDGE and 0.0 < filled_e < 1.0:
                cw = fm.horizontalAdvance(ch)
                gr = QLinearGradient(cx, 0.0, cx + cw, 0.0)
                gr.setColorAt(0.0, karaoke_color(g, filled_e + 0.5, dim_alpha))
                gr.setColorAt(1.0, karaoke_color(g, filled_e - 0.5, dim_alpha))
                fill = QBrush(gr)
            else:
                fill = QBrush(karaoke_color(g, filled_e, dim_alpha))

            moved = dxc or dyc or deg or scal != 1.0
            if moved:
                p.save()
                px_ = cx + fm.horizontalAdvance(ch) / 2.0   # 绕字符底部中心变换
                p.translate(px_ + dxc, y + dyc)
                if deg:
                    p.rotate(deg)
                if scal != 1.0:
                    p.scale(scal, scal)
                p.translate(-px_, -y)
            ch_path = QPainterPath()
            ch_path.addText(QPointF(cx, y), font, ch)
            if halo_on:
                for pen in halo:
                    p.strokePath(ch_path, pen)
            p.fillPath(ch_path, fill)
            if moved:
                p.restore()

    def _draw_plain(self, p: QPainter, text: str, x: float, y: float, font: QFont,
                    fm: QFontMetrics, halo_w: float, alpha: int, halo_on: bool = True):
        if not text:
            return
        path = QPainterPath()
        path.addText(QPointF(x, y), font, text)
        if halo_on:
            for pen in self._halo_pens(halo_w):
                p.strokePath(path, pen)
        p.fillPath(path, QColor(255, 255, 255, alpha))

    def _draw_trans(self, p: QPainter, text: str, x: float, y: float,
                    font: QFont, fm: QFontMetrics):
        """翻译 / 音译行：比原文小一号；封面色向白色提亮后再用，避免像超链接"""
        if not text:
            return
        c = self.accent2
        # 向白提亮 72%（v2.4.16 起，原为 48%）：保留一丝封面色的温度，但整体读起来是
        # 柔和的中性浅灰，不会像超链接。提亮比例跟着描边一起调——描边变淡之后，
        # 翻译行必须自身更"实"才不会跟着糊掉。
        k = 0.72
        r = int(c.red() * (1 - k) + 255 * k)
        g = int(c.green() * (1 - k) + 255 * k)
        b = int(c.blue() * (1 - k) + 255 * k)
        path = QPainterPath()
        path.addText(QPointF(x, y), font, text)
        for pen in self._halo_pens(self._px(2.4)):
            p.strokePath(path, pen)
        p.fillPath(path, QColor(r, g, b, 196))

    def _paint_time(self, p: QPainter, right: float, bar_y: float, frac: float,
                    halo: bool = False) -> float:
        """在进度条右端画「当前 / 总长」，返回进度条可用的最右 x

        halo：无卡片底的样式用，加黑色描边保证浅色桌面上也能读
        """
        tstr = self._time_text()
        if not tstr:
            return right
        f = self._font_reg(self._px(11))
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(tstr)
        pos = QPointF(right - tw, bar_y + fm.ascent() - 3)
        path = QPainterPath()
        path.addText(pos, f, tstr)
        if halo:
            for pen in self._halo_pens(self._px(2.2)):
                p.strokePath(path, pen)
            p.fillPath(path, QColor(255, 255, 255, 212))
        else:
            p.fillPath(path, QColor(255, 255, 255, 142))
        return right - tw - 10

    def _paint_equalizer(self, p: QPainter, x: float, y: float, playing: bool):
        p.save()
        p.setPen(Qt.NoPen)
        now = time.monotonic()
        for i in range(3):
            if playing:
                h = 4.5 + ((3.5 * abs(1.7 + i * 0.9 + now * (3.1 + i * 0.7))) % 3.5)
            else:
                h = (2.5, 4.0, 2.0)[i]
            alpha = 205 if playing else 110
            p.setBrush(QColor(self.accent2.red(), self.accent2.green(),
                              self.accent2.blue(), alpha))
            p.drawRoundedRect(QRectF(x + i * 6, y + 9 - h, 3.5, h), 1.5, 1.5)
        p.restore()

    def _paint_cover(self, p: QPainter, x: float, y: float, size: float = COVER, radius: float = 13):
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, size, size), radius, radius)
        p.save()
        p.setClipPath(path)
        if self.cover_pix and not self.cover_pix.isNull():
            want = int(size * 2)
            if self._cover_scaled is None or self._cover_scaled_size != want:
                # 缩放结果缓存，避免每帧 SmoothTransformation
                self._cover_scaled = self.cover_pix.scaled(
                    want, want, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self._cover_scaled_size = want
            scaled = self._cover_scaled
            sx = x - (scaled.width() / 2 - size) / 2
            sy = y - (scaled.height() / 2 - size) / 2
            p.drawPixmap(QPointF(sx, sy), scaled)
        else:
            grad = QLinearGradient(x, y, x + size, y + size)
            grad.setColorAt(0, QColor(self.accent1.red(), self.accent1.green(),
                                      self.accent1.blue(), 90))
            grad.setColorAt(1, QColor(self.accent2.red(), self.accent2.green(),
                                      self.accent2.blue(), 70))
            p.fillPath(path, QBrush(grad))
            p.setPen(QPen(QColor(255, 255, 255, 160)))
            f = QFont("Segoe UI Symbol")
            f.setPixelSize(int(size * 0.42))
            p.setFont(f)
            p.drawText(QRectF(x, y, size, size), Qt.AlignCenter, "♪")
        p.restore()
        self._stroke(p, path, QPen(QColor(255, 255, 255, 34), 1))

    def _paint_waiting(self, p: QPainter, pill: QRectF):
        p.setFont(self._font_cur(self._px(22)))
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(pill.adjusted(0, 10, 0, -26), Qt.AlignCenter, "等待播放…")
        p.setFont(self._font_reg(self._px(13)))
        p.setPen(QColor(255, 255, 255, 95))
        p.drawText(pill.adjusted(0, 34, 0, -6), Qt.AlignCenter,
                   "在 QQ音乐 / 网易云 播放歌曲即可显示歌词")

    # ---------------- 交互 ----------------

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            idx = self._ctrl_button_at(e.position())
            if idx == 0:
                self.media_command("prev")
                return
            if idx == 1:
                self.media_command("toggle")
                return
            if idx == 2:
                self.media_command("next")
                return
            if idx == 3:
                self.open_saver()
                return
            if idx == 4:
                self._toggle_lock()
                return
            if idx == 5:
                self._open_panel()
                return
            if not self.locked:
                self._drag_offset = (e.globalPosition().toPoint()
                                     - self.frameGeometry().topLeft())
        elif e.button() == Qt.RightButton:
            self._show_menu(e.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.media_command("toggle")

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            self._clamp_into_screen()    # 拖不到屏幕外面去（松手也不会留一半在外）

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            if self._current_position_key() == POS_FREE:
                self.pos_preset = POS_FREE       # 手动拖过就不再套预设
            self._clamp_into_screen()
            self._save_position()

    def _toggle_action(self, menu, text, checked, slot):
        a = menu.addAction(text)
        a.setCheckable(True)
        a.setChecked(checked)
        a.triggered.connect(lambda: slot(a.isChecked()))
        return a

    def _build_context_menu(self) -> QMenu:
        """构建右键菜单（与托盘菜单共用一套皮肤）。

        单独拆成一个方法是为了**可测**：`_show_menu` 里的 `exec()` 会阻塞，
        测试没法驱动，拆开后测试可以直接拿到菜单对象、断言它确实套了 `menu_qss`
        ——右键菜单曾经漏掉这一步，于是弹出的是系统原生白底菜单。
        """
        menu = QMenu(self)
        # 菜单项配图标（选中态自动换深色，见 make_menu_icon）：纯文字的菜单一眼扫不出
        # 类别，加了图标列之后"播放控制 / 刷新 / 退出"能瞬间分辨。
        act_panel = menu.addAction(make_menu_icon("gear"), "设置面板…")
        act_panel.triggered.connect(self._open_panel)
        menu.addSeparator()
        a_prev = menu.addAction(make_menu_icon("prev"), "上一首")
        a_prev.triggered.connect(lambda: self.media_command("prev"))
        _playing = self.status == "PLAYING"
        a_toggle = menu.addAction(make_menu_icon("pause" if _playing else "play"),
                                  "暂停" if _playing else "播放")
        a_toggle.triggered.connect(lambda: self.media_command("toggle"))
        a_next = menu.addAction(make_menu_icon("next"), "下一首")
        a_next.triggered.connect(lambda: self.media_command("next"))
        a_refetch = menu.addAction(make_menu_icon("refresh"), "重新获取歌词")
        a_refetch.triggered.connect(self._refresh_lyrics)
        menu.addSeparator()

        m_style = menu.addMenu("样式")
        for key, name in STYLE_NAMES.items():
            a = m_style.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.style_mode == key)
            a.triggered.connect(lambda _=False, k=key: self.set_style_mode(k))

        m_dm = menu.addMenu("显示模式")
        for name, key in (("常驻桌面", "desktop"), ("置顶悬浮", "topmost")):
            a = m_dm.addAction(name)
            a.setCheckable(True)
            a.setChecked(self.display_mode == key)
            a.triggered.connect(lambda _=False, k=key: self.set_display_mode(k))

        m_off = menu.addMenu("歌词偏移（当前 %+.1fs）" % self.offset)
        a_early = m_off.addAction("提前 0.5 秒")
        a_early.triggered.connect(lambda: self.set_offset(self.offset + 0.5))
        a_late = m_off.addAction("延后 0.5 秒")
        a_late.triggered.connect(lambda: self.set_offset(self.offset - 0.5))
        a_zero = m_off.addAction("偏移归零")
        a_zero.triggered.connect(lambda: self.set_offset(0.0))

        m_float = menu.addMenu("悬浮窗")
        self._toggle_action(m_float, "显示专辑封面", self.show_cover, self.set_show_cover)
        self._toggle_action(m_float, "显示翻译 / 音译", self.show_trans, self.set_show_trans)
        self._toggle_action(m_float, "显示进度时间", self.show_time, self.set_show_time)
        self._toggle_action(m_float, "氛围光晕", self.glow, self.set_glow)
        self._toggle_action(m_float, "暂停自动淡出", self.pause_fade, self.set_pause_fade)
        self._toggle_action(m_float, "鼠标点击穿透", self.click_through, self.set_click_through)
        self._toggle_action(m_float, "锁定位置（禁止拖动）", self.locked, self.set_locked)
        m_float.addSeparator()
        act_clear = m_float.addAction("清空歌词缓存")
        act_clear.triggered.connect(self._clear_cache)

        # 摆放位置（借鉴 FluentFlyout 的浮层位置定制）
        self._build_pos_menu(menu)
        menu.addSeparator()
        act_quit = menu.addAction(make_menu_icon("quit"), "退出")
        act_quit.triggered.connect(self._quit)
        # 右键菜单每次弹出重建，但**必须套皮肤**：不套就是系统原生白底菜单，
        # 和整套深色 UI 直接打架。子菜单（样式/显示模式/摆放位置…）会继承这份样式表。
        menu.setStyleSheet(menu_qss(self.accent1))
        return menu

    def _show_menu(self, global_pos):
        self._build_context_menu().exec(global_pos)

    def _clear_cache(self):
        for name in os.listdir(CACHE_DIR):
            if name.endswith(".json"):
                try:
                    os.remove(os.path.join(CACHE_DIR, name))
                except OSError:
                    pass


LyricOverlay._restore_position_done = False


# ======================================================================
# 设置面板（深色玻璃质感，跟随封面主色换肤）
# ======================================================================

class Switch(QWidget):
    """iOS 风格开关：圆角轨道 + 滑动圆钮，比 QCheckBox 现代得多

    交互即调色：轨道在「关=灰 / 开=主色」之间随圆钮位置插值，切换有 150ms 缓动。
    """

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None, w: int = 44, h: int = 24):
        super().__init__(parent)
        self._on = bool(checked)
        self._w, self._h = int(w), int(h)
        self._accent = QColor(DEFAULT_ACCENT1)
        self._knob = 1.0 if self._on else 0.0
        self._hover = False
        self.setFixedSize(self._w, self._h)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_knob)

    def _set_knob(self, v):
        self._knob = float(v)
        self.update()

    def set_accent(self, c: QColor):
        self._accent = QColor(c)
        self.update()

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, v: bool, emit: bool = False, animate: bool = False):
        v = bool(v)
        same = (v == self._on)
        self._on = v
        if same and not animate:
            self._knob = 1.0 if v else 0.0
            self.update()
            return
        end = 1.0 if v else 0.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._knob)
            self._anim.setEndValue(end)
            self._anim.start()
        else:
            self._knob = end
            self.update()
        if emit:
            self.toggled.emit(v)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.setChecked(not self._on, emit=True, animate=True)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self._w - 1, self._h - 1)
        rad = r.height() / 2.0
        k = self._knob
        # 轨道：关=深灰，开=主色，按圆钮位置插值
        off = QColor(56, 61, 74)
        ac = QColor(self._accent)
        track = QColor(int(off.red() + (ac.red() - off.red()) * k),
                       int(off.green() + (ac.green() - off.green()) * k),
                       int(off.blue() + (ac.blue() - off.blue()) * k))
        if self._hover:
            track = track.lighter(114)                 # 悬停时整条轨道提亮一档
        # 轨道竖向渐变（顶暗底亮）：读成"有深度的槽"，纯平色会像贴纸。
        # 描边改用暗色而非白色——开关是"嵌进面板"的控件，白边会让它浮起来。
        tg = QLinearGradient(0, r.top(), 0, r.bottom())
        tg.setColorAt(0.0, track.darker(116))
        tg.setColorAt(1.0, track.lighter(108))
        p.setPen(QPen(QColor(0, 0, 0, 96), 1))
        p.setBrush(QBrush(tg))
        p.drawRoundedRect(r, rad, rad)
        # 圆钮：先落影再画钮体——没有落影的钮压在轨道上会"贴"成一片
        pad = 3.0
        kr = rad - pad
        kx = r.left() + pad + kr + k * (r.width() - 2 * (pad + kr))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QPointF(kx, r.center().y() + 1.0), kr, kr)
        p.setBrush(QColor(250, 252, 255))
        p.drawEllipse(QPointF(kx, r.center().y()), kr, kr)
        p.end()


class Segmented(QWidget):
    """分段选择器：2~4 个互斥选项，选中段用主色填充，比下拉框更直观"""

    changed = Signal(str)

    def __init__(self, items, current=None, parent=None, h: int = 32):
        super().__init__(parent)
        self._items = [(i, i) if isinstance(i, str) else (i[0], i[1]) for i in items]
        self._cur = current if current is not None else self._items[0][0]
        self._h = int(h)
        self._accent = QColor(DEFAULT_ACCENT1)
        self.setFixedHeight(self._h)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._idx_anim = QVariantAnimation(self)
        self._idx_anim.setDuration(160)
        self._idx_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._idx = float(self._index_of(self._cur))
        self._hover_i = -1
        self.setMouseTracking(True)                 # 未选中段要能响应悬停
        self._idx_anim.valueChanged.connect(self._set_idx)

    def _set_idx(self, v):
        self._idx = float(v)
        self.update()

    def _index_of(self, key) -> int:
        for i, (k, _l) in enumerate(self._items):
            if k == key:
                return i
        return 0

    def value(self) -> str:
        return self._cur

    def sizeHint(self):
        # 必须有真实 sizeHint，否则 Expanding 策略下在面板布局里塌缩成 0 宽（控件看不见）
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(max(11, int(self._h * 0.42)))
        f.setBold(True)
        fm = QFontMetrics(f)
        pad = 10
        inner = 14                       # 选中滑块左右内边距
        total = pad * 2 + inner * 2 * len(self._items)
        for _k, label in self._items:
            total += fm.horizontalAdvance(label)
        return QSize(max(96, total), self._h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_accent(self, c: QColor):
        self._accent = QColor(c)
        self.update()

    def setValue(self, key, emit: bool = False, animate: bool = True):
        if key is None:
            return
        i = self._index_of(key)
        self._cur = self._items[i][0]
        if animate and abs(self._idx - i) > 0.01:
            self._idx_anim.stop()
            self._idx_anim.setStartValue(self._idx)
            self._idx_anim.setEndValue(float(i))
            self._idx_anim.start()
        else:
            self._idx = float(i)
            self.update()
        if emit:
            self.changed.emit(self._cur)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        n = len(self._items)
        if n == 0:
            return
        seg = self.width() / n
        i = min(n - 1, max(0, int(e.position().x() // seg)))
        if self._items[i][0] != self._cur:
            self.setValue(self._items[i][0], emit=True)

    def mouseMoveEvent(self, e):
        n = max(1, len(self._items))
        i = min(n - 1, max(0, int(e.position().x() // (self.width() / n))))
        if i != self._hover_i:
            self._hover_i = i
            self.update()

    def leaveEvent(self, e):
        if self._hover_i != -1:
            self._hover_i = -1
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rad = h / 2.0
        # 轨道要比卡片底**明显更深**才读得出"凹槽"。原来用 #181b22，跟卡片底色
        # （#1c2029~#14171e）几乎一样，轨道整个糊进卡片里，看着像选项在飘。
        # 轨道要比卡片底**明显更深**才读得出"凹槽"。原来用 #181b22，跟卡片底色
        # （#1c2029~#14171e）几乎一样，轨道整个糊进卡片里，看着像选项在飘。
        # 再用竖向渐变把顶部压得更暗，凹槽就有了"深度"而不只是一块深色。
        tg = QLinearGradient(0, 0, 0, h)
        tg.setColorAt(0.0, QColor(7, 9, 13))
        tg.setColorAt(1.0, QColor(20, 24, 31))
        p.setPen(QPen(QColor(0, 0, 0, 120), 1))
        p.setBrush(QBrush(tg))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), rad, rad)
        n = max(1, len(self._items))
        seg = w / n
        pad = 3.0
        pw, ph = seg - 2 * pad, h - 2 * pad
        pr = ph / 2.0
        sx = pad + self._idx * seg
        ac = QColor(self._accent)
        # 选中滑块：先落影、再铺「顶亮底暗」的主色渐变 —— 读成浮在槽上的一块实体，
        # 而不是"槽里刷了层颜色"。
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 84))
        p.drawRoundedRect(QRectF(sx, pad + 1.5, pw, ph), pr, pr)
        pg = QLinearGradient(0, pad, 0, pad + ph)
        pg.setColorAt(0.0, ac.lighter(124))
        pg.setColorAt(1.0, ac.darker(106))
        p.setBrush(QBrush(pg))
        p.drawRoundedRect(QRectF(sx, pad, pw, ph), pr, pr)
        # 文字
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(max(11, int(h * 0.42)))
        f.setBold(True)
        p.setFont(f)
        for i, (_k, label) in enumerate(self._items):
            sel = abs(self._idx - i) < 0.5
            if sel:
                p.setPen(QColor(18, 20, 26))
            elif i == self._hover_i:
                p.setPen(QColor(214, 221, 233))        # 悬停的未选项提亮，给点击预期
            else:
                p.setPen(QColor(178, 185, 198))
            p.drawText(QRectF(i * seg, 0, seg, h), Qt.AlignCenter, label)
        p.end()


def make_card(title: str, parent=None):
    """现代卡片：圆角深色底 + 主色小标题，替代老式 QGroupBox

    返回 (card, body_layout)，body_layout 由调用方继续 addWidget。
    """
    card = QWidget(parent)
    card.setObjectName("card")
    card.setAttribute(Qt.WA_StyledBackground, True)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(16, 13, 16, 15)
    lay.setSpacing(10)
    lb = QLabel(title)
    lb.setObjectName("cardtitle")
    lay.addWidget(lb)
    return card, lay


def make_row(label: str, *widgets: QWidget, hint: str = ""):
    """一行设置：左侧文字（可带小字提示）+ 右侧控件（控件靠右，视觉更整齐）"""
    row = QWidget()
    row.setAttribute(Qt.WA_StyledBackground, True)
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lb = QLabel(label)
    lb.setObjectName("rowlabel")
    h.addWidget(lb)
    if hint:
        tip = QLabel(hint)
        tip.setObjectName("rowhint")
        h.addWidget(tip)
    h.addStretch(1)
    for w in widgets:
        h.addWidget(w)
    return row


class AmbientSaver(QWidget):
    """全屏氛围屏保：黑底防烧屏

    设计要点（OLED 防烧屏）：
      · 纯黑打底 —— 黑像素在 OLED 上不发光，本身就是最省屏的待机态
      · 所有元素（时钟/封面光晕/歌词）都以不同周期缓慢漂移，避免像素长时间静止
      · 亮度低（时钟约 120/255），并做极慢的呼吸，不出现高亮静止块
      · 视频/音频继续播放，但屏保只画极简信息，长时间挂着也不会烧屏
    """

    finished = Signal()

    # ---- 屏保版式常量：所有比例只在这里出现（paintEvent 不再自己写字号与坐标）----
    SAFE_X = 0.055          # 左右安全边距（占宽）
    SAFE_Y = 0.055          # 上下安全边距（占高）
    ZONE_GAP = 0.045        # 文字区与动画带之间的最小空隙（占高）—— 保证两者永不相交
    TEXT_DRIFT = 0.075      # 文字块的横向换位幅度（占宽），从安全边距里预留出来

    # 文字区里**必须**留给 AOD 换位的比例。
    # 没有这条约束时，4 行版式在 16:9 上正好把文字区填满（block_h ≈ tz_h），
    # 换位行程只剩零点几像素 —— 换位代码在跑，但一点位移都没有，等于没写。
    # 于是自动适配会优先缩字号把它让出来，而不是让"防烧屏"悄悄失效。
    TRAVEL_MIN = 0.20
    K_MIN = 0.60            # 为让出行程而缩字号的下限（缩到这里就改走"塞进整区"的退路）
    K_FLOOR = 0.34          # 连整个文字区都塞不下时的极限下限
    # 文字块高度上限（占 min(w,h)）。
    # 没有它的时候，字号的唯一约束是各自风格的文字区高度：particle/orbits 的动画带
    # 占掉上半屏，文字区就小，时钟被压到 ~135px；bars/minimal 的文字区大得多，
    # 同一个时钟能到 183px —— 切主题时时钟会明显跳大跳小。
    # 用一个统一上限锁住，四种风格的时钟尺寸才基本一致（实测 151~164px）。
    # 取值是"观感 vs 防烧屏"的折中：再压小能换到更大换位行程，但时钟会显得单薄。
    TEXT_MAX_H = 0.340

    # AOD 式换位：让同一簇文字长期不在同一处点亮，摊薄每个像素的占空比。
    # 只做几像素的抖动是防不住烧屏的 —— 时钟像素的**平均**位置不变，占空比依旧接近 1。
    ANCHORS = 3             # 文字区内的驻留档位（顶 / 中 / 底）
    ANCHOR_HOLD = 200.0     # 每档驻留秒数
    ANCHOR_MOVE = 8.0       # 换档过渡秒数（smoothstep，不突跳）

    # 长时间空闲渐进变暗（类似显示器的 ASBL）：前 DIM_START 秒满亮，
    # 之后 DIM_RAMP 秒内线性压到 DIM_FLOOR —— 挂机越久越安静，也更省屏。
    DIM_START = 600.0
    DIM_RAMP = 3000.0
    DIM_FLOOR = 0.62

    def __init__(self, ov: LyricOverlay):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.ov = ov
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setCursor(Qt.BlankCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._t0 = time.monotonic()
        self._done = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(100)
        # ---- 粒子场（惰性构建，防烧屏：粒子自身极慢漂移 + 低亮度） ----
        self._particles = None          # [(x, y, z, vx, vy, r), ...]
        self._p_geom = None             # 生成时的 (w,h,带顶部,带高)；变化后重建
        self._p_t0 = time.monotonic()   # 粒子相位基准

    # ---------- 生命周期 ----------

    def start(self):
        scr = QApplication.screenAt(QApplication.primaryScreen().geometry().center()) \
            or QApplication.primaryScreen()
        self.setGeometry(scr.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)

    def finish(self):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # ---------- 输入即退出 ----------

    def keyPressEvent(self, e):
        self.finish()

    def mousePressEvent(self, e):
        self.finish()

    def wheelEvent(self, e):
        self.finish()

    def closeEvent(self, e):
        self._done = True
        self._timer.stop()
        self.finished.emit()

    # ---------- 粒子系统（3D 粒子星云，极简不晕） ----------

    def _ensure_particles(self, w: int, h: int, band):
        """懒构建粒子场；尺寸或动画带变化时重建。

        粒子位置**按动画带生成**（不是按整屏）—— 原来按整屏铺，
        结果星云从上到下糊满屏幕，时钟数字上和底部歌词上都压着粒子。
        """
        key = (w, h, round(band.top(), 1), round(band.height(), 1))
        if self._particles is not None and self._p_geom == key:
            return
        n = int(max(160, min(520, (w * h) / 4000)))      # 密度自适应
        cx, cy = w / 2.0, band.center().y()
        rx = min(w * 0.46, band.height() * 1.60)         # 横半径
        ry = band.height() * 0.44                        # 纵半径：一律落在带内
        pts = []
        for _ in range(n):
            z = 0.18 + 0.82 * random.random()            # z∈[0.18,1] 越远越暗
            # 密度剖面：约六成挤进核心（幂次把它压向 0），其余在外层弥散。
            # 旧版是 rr = 0.10 + 0.88*rand 的均匀铺 —— 铺出来是"一盒子灰尘"，
            # 没有星云该有的核心—晕结构。
            if random.random() < 0.60:
                rr = random.random() ** 2.10             # 核心簇
            else:
                rr = 0.24 + 0.76 * random.random()       # 外层弥散
            rr_y = rr * (0.58 + 0.42 * random.random())  # 纵向再压扁些，星云是扁的
            a = random.uniform(0.0, math.pi * 2)
            pts.append([cx + math.cos(a) * rr * rx,
                        cy + math.sin(a) * rr_y * ry,
                        z,
                        random.uniform(-2.6, 2.6), random.uniform(-1.2, 1.2),
                        # 尺寸分层：多数是细尘，少数是亮点（幂次 > 1 压向小值）
                        0.9 + 3.0 * (random.random() ** 2.6),
                        random.uniform(0.0, math.pi * 2.0),
                        1 if random.random() > 0.66 else 0])   # 约 1/3 用副色调
        self._particles = pts
        self._p_geom = key
        self._p_t0 = time.monotonic()

    def _draw_particles(self, p: QPainter, w: int, h: int, plan):
        """3D 粒子「星云」：绕动画带中心缓慢公转 + 一丝呼吸，低亮度不烧屏。

        粒子按带生成、绘制时又裁到带内，并且**越靠带边缘越暗** ——
        个别粒子漂到带边被裁时是"淡出"，不会硬生生切出一条直边。
        """
        band = plan["band"]
        self._ensure_particles(w, h, band)
        t = time.monotonic() - self._p_t0
        # 用 plan 里已经带游移的中心（不是 band 的几何中心）：星云整体缓慢迁移，
        # 核心才不会变成一个长期不动的亮点。
        cxm, cym = plan["bcx"], plan["bcy"]
        breathe, dim = plan["breathe"], plan["dim"]
        rot = t * (2 * math.pi / 44.0)             # 44s 一圈，很慢不易晕
        c1, c2 = self.ov.accent1, self.ov.accent2
        col1 = (c1.red(), c1.green(), c1.blue())
        col2 = (c2.red(), c2.green(), c2.blue())
        half_h = max(1.0, band.height() / 2.0)
        for pt in self._particles:
            x, y, z, vx, vy, r0, ph, tint = pt
            ca, sa = math.cos(rot * z), math.sin(rot * z)
            xr = (x - cxm) * ca - (y - cym) * sa + cxm
            yr = (x - cxm) * sa + (y - cym) * ca + cym
            # 自身缓慢漂移（有界正弦，不越界；避免旧写法用 % 把负向漂移绕到屏幕右侧）
            xr += math.sin(t * 0.11 + ph) * (w * 0.030)
            yr += math.cos(t * 0.08 + ph) * (h * 0.016)
            sc = (0.6 + 0.9 * z)                   # 近大远小
            rr = r0 * sc
            if rr < 0.4:
                continue
            edge = min(1.0, abs(yr - cym) / half_h)   # 0 带中心 → 1 带边缘
            fade = 1.0 - edge * edge
            a = int((24 + 66 * z) * (0.82 + 0.18 * breathe) * fade * dim)
            if a <= 2:
                continue
            ar, ag, ab = col2 if tint else col1    # 双色混合，星云有层次
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ar, ag, ab, a))
            p.drawEllipse(QPointF(xr, yr), rr, rr)

    @staticmethod
    def _band_drift(t, band: QRectF):
        """动画内容整体的极慢游移（双轴 Lissajous，周期 257s / 173s，互不成整数比）。

        为什么需要它：星云核心、星轨圆心这些元素只绕**自身中心**旋转 ——
        像素的平均位置根本没变，占空比照样接近 1（实测周期内平均亮度到 85/255）。
        让整团内容在带内缓慢迁移，核心才真的换地方。
        振幅刻意压小（宽 5.5%、高 11%），肉眼看是"在漂"，不是"在动"。
        """
        return (math.sin(t * 2 * math.pi / 257.0) * band.width() * 0.055,
                math.cos(t * 2 * math.pi / 173.0) * band.height() * 0.11)

    @staticmethod
    def _fill_band_glow(p: QPainter, band: QRectF, ar: int, ag: int, ab: int, a0: float,
                        cx: float = None, cy: float = None):
        """把一圈径向光晕**内切**进动画带里填满。

        为什么不是直接 `p.fillRect(band, 圆渐变换刷)`：圆的半径按带的长边算，
        到带的上下边时渐变还远没衰减到 0，fillRect 一刀切下去，就在带的边界
        留下一条可见的亮度阶跃（实测阶跃 6~13/255，肉眼能看见一条横向接缝，
        浅色壁纸上尤其明显）。改成先把画布纵向压扁、再填一个内切正方形里的圆：
        椭圆恰好内切于动画带，四条边中点与四个角处 alpha 精确为 0 ——
        接缝不是"调参调到看不见"，而是数学上不存在。
        """
        if cx is None or cy is None:
            cx, cy = band.center().x(), band.center().y()
        hw = max(1.0, band.width() / 2.0)
        hh = max(1.0, band.height() / 2.0)
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, hh / hw)                    # 圆 → 压成带的内切椭圆
        grad = QRadialGradient(QPointF(0.0, 0.0), hw)
        grad.setColorAt(0.0, QColor(ar, ag, ab, int(a0)))
        grad.setColorAt(0.45, QColor(ar, ag, ab, int(a0 * 0.30)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(-hw, -hw, hw * 2.0, hw * 2.0), QBrush(grad))
        p.restore()

    def _draw_particle_glow(self, p: QPainter, w: int, h: int, plan):
        """粒子模式中央的极淡封面光晕（收在动画带内，文字落在干净的黑上）。"""
        br, dim = plan["breathe"], plan["dim"]
        c = self.ov.accent1
        self._fill_band_glow(p, plan["band"], c.red(), c.green(), c.blue(),
                             (20 + 12 * br) * dim, plan["bcx"], plan["bcy"])

    # ---------- 版式：屏保唯一的布局来源 ----------

    def _anchor_pos(self, t) -> float:
        """文字块在文字区内的归一化纵向位置 0(顶)..1(底)。

        按 ANCHORS 个档位循环驻留，档间用 smoothstep 过渡（不突跳）。
        这是 AOD 的做法：只做几像素抖动是防不住烧屏的 —— 时钟那几个字的像素
        **平均**位置没变，占空比依旧接近 1；整簇换位才真正摊薄了每个像素。
        """
        n = max(2, self.ANCHORS)
        period = self.ANCHOR_HOLD + self.ANCHOR_MOVE
        tt = t % (period * n)
        i = int(tt // period)
        frac = tt - i * period
        a = i / (n - 1.0)
        b = ((i + 1) % n) / (n - 1.0)
        if frac <= self.ANCHOR_HOLD:
            return a
        m = (frac - self.ANCHOR_HOLD) / self.ANCHOR_MOVE
        return a + (b - a) * (m * m * (3.0 - 2.0 * m))

    def _dim(self, t) -> float:
        """长时间空闲后的整体亮度系数（显示器 ASBL 的软件版）"""
        if t <= self.DIM_START:
            return 1.0
        k = min(1.0, (t - self.DIM_START) / self.DIM_RAMP)
        return 1.0 - (1.0 - self.DIM_FLOOR) * k

    def _plan(self, w, h, t):
        """算出这一帧的版式：动画带 / 文字区 / 每行文字的字号·颜色·基线。

        为什么要有这个函数（而不是继续在 paintEvent 里各写各的 y 比例）：
          · 原来各风格的 y 位置按 h 的比例写死，字号却按 min(w,h) 算，两边各算各的，
            从没校验过彼此的实际高度。于是 bars 的日期直接压在歌词上、
            orbits 的日期被挤到屏幕最底部（离下边缘只剩几十像素）、
            particle 的粒子铺满全屏、连时钟数字上都压着粒子。
          · 现在文字块的**真实高度**由 QFontMetrics 量出来，再在文字区里定位；
            动画另占一条带，绘制时裁剪到带内。文字区与动画带之间留 ZONE_GAP，
            两者在构造上就不可能相交 —— 遮挡是被结构杜绝的，不是调参凑出来的。
          · paintEvent 与回归测试读同一个函数，「断言不重叠」与「画出来不重叠」
            才是同一件事，不会各算各的然后悄悄漂移。
        """
        ov = self.ov
        style = ov.saver_style if ov.saver_style in ("particle", "minimal", "bars", "orbits") \
            else "particle"
        sx, sy = w * self.SAFE_X, h * self.SAFE_Y
        m = min(w, h)
        gap = h * self.ZONE_GAP
        # 面板里的实时预览只有 252x142：按正常比例画出来字会小到看不清。
        # 小尺寸切「紧凑模式」——少一行、字号相对放大。
        compact = m < 260

        cur = ov._current_text or ""
        nxt = ov._next_text or ""

        # ---- 1. 动画带 与 文字可用区（都夹在安全边距之内）----
        # 带高比上一版各收 2~3 个百分点：文字区跟着变高，自动适配就不必为了
        # 让出 TRAVEL_MIN 的换位行程把字号缩得太狠。
        if style == "particle":
            band = QRectF(0.0, 0.0, float(w), h * 0.49)
            tz_top, tz_bot = band.bottom() + gap, h - sy
        elif style == "bars":
            band = QRectF(0.0, h * 0.735, float(w), h * 0.265)
            tz_top, tz_bot = sy, band.top() - gap
        elif style == "orbits":
            band = QRectF(0.0, sy * 0.6, float(w), h * 0.47)
            tz_top, tz_bot = band.bottom() + gap, h - sy
        else:                                   # minimal：没有动画，整块安全区都给文字
            band = None
            tz_top, tz_bot = h * 0.14, h * 0.86

        now = time.localtime()
        hhmm = time.strftime("%H:%M", now)
        date_s = "%s  %s" % (time.strftime("%Y 年 %m 月 %d 日", now), WEEKDAY_CN[now.tm_wday])

        def build(k):
            cpx = max(12, int(m * 0.170 * k))
            f_c = QFont(ov.font_family or FONT_CUR)
            f_c.setPixelSize(cpx)
            f_c.setBold(False)
            fm_c = QFontMetrics(f_c)
            dpx = max(10, int(m * 0.0215 * k))
            f_d = QFont(ov.font_family or FONT_REG)
            f_d.setPixelSize(dpx)
            fm_d = QFontMetrics(f_d)
            lpx = max(12, int(m * 0.0285 * k))
            f_l = QFont(ov.font_family or FONT_CUR)
            f_l.setPixelSize(lpx)
            fm_l = QFontMetrics(f_l)
            npx = max(10, int(m * 0.0195 * k))
            f_n = QFont(ov.font_family or FONT_REG)
            f_n.setPixelSize(npx)
            fm_n = QFontMetrics(f_n)

            # 面板缩略图（252x142 那档）只放 clock + lyric：屏保的看点是歌词，
            # 空间不够时该让位的是日期，不是歌词（旧版正好相反，缩略图里只剩日期）。
            rows = [("clock", f_c, fm_c, hhmm)]
            if compact:
                rows.append(("lyric", f_l, fm_l, cur) if cur
                            else ("date", f_d, fm_d, date_s))
            else:
                rows.append(("date", f_d, fm_d, date_s))
                if cur:
                    rows.append(("lyric", f_l, fm_l, cur))
                if nxt:
                    rows.append(("next", f_n, fm_n, nxt))
            # 行距整体收紧（原 0.013/0.050/0.016）：把省下的高度还给字号和换位行程
            gs = [max(5.0, m * 0.011), max(10.0, m * 0.034), max(4.0, m * 0.013)]
            gs = gs[:max(0, len(rows) - 1)]
            hh = sum(fm.height() for _, _, fm, _ in rows) + sum(gs)
            return rows, gs, hh

        # ---- 2. 量高 + 自动适配（三级退路）----
        #   ① 缩字号，先把 TRAVEL_MIN 的换位行程留出来（防烧屏优先）
        #   ② 字号缩到 K_MIN 还让不出行程 → 继续缩到能塞进整个文字区（不丢行）
        #   ③ 连整区都塞不下 → 按重要度丢行（next → date），永远保住 clock + lyric
        tz_h = max(1.0, tz_bot - tz_top)
        fit_target = min(tz_h * (1.0 - self.TRAVEL_MIN), m * self.TEXT_MAX_H)
        rows, gs, block_h = build(1.0)
        k = 1.0
        if block_h > fit_target:
            # 先用线性估计一步到位：块高 ≈ 各行字高之和(k 近似线性) + 行距(与 k 无关)。
            # 早先用固定 6% 的阶梯逐级下探，落点最多会多缩 5%，白白丢掉一圈字号。
            body1 = block_h - sum(gs)
            if body1 > 0:
                k = max(self.K_MIN, min(1.0, (fit_target - sum(gs)) / body1))
                rows, gs, block_h = build(k)
            while k > self.K_MIN and block_h > fit_target:
                k = max(self.K_MIN, k * 0.98)
                rows, gs, block_h = build(k)
            while k > self.K_FLOOR and block_h > tz_h:
                k = max(self.K_FLOOR, k * 0.94)
                rows, gs, block_h = build(k)
        while block_h > tz_h and len(rows) > 2:
            for drop in ("next", "date"):
                if any(r[0] == drop for r in rows):
                    rows = [r for r in rows if r[0] != drop]
                    break
            gs = gs[:max(0, len(rows) - 1)]
            block_h = sum(fm.height() for _, _, fm, _ in rows) + sum(gs)

        # ---- 3. 定位：块在文字区内按 anchor 驻留（AOD 式换位）----
        anchor = self._anchor_pos(t)
        block_top = tz_top + max(0.0, tz_h - block_h) * anchor

        # 动画内容整体游移的中心（见 _band_drift）：光晕 / 星云 / 星轨共用一个中心，
        # 三种风格才会一起漂，而不是各漂各的。
        bcx, bcy = w / 2.0, (band.center().y() if band is not None else h * 0.5)
        if band is not None:
            _bdx, _bdy = self._band_drift(t, band)
            bcx += _bdx
            bcy += _bdy

        breathe = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 53.0)
        dim = self._dim(t)
        COL = {"clock": QColor(236, 240, 246), "date": QColor(150, 158, 172),
               "lyric": QColor(ov.accent1), "next": QColor(158, 166, 180)}
        BASE = {"clock": 104, "date": 74, "lyric": 122, "next": 56}

        lines = []
        y = block_top
        for i, (key, f, fm, text) in enumerate(rows):
            if i:
                y += gs[i - 1]
            lines.append({"key": key, "font": f, "fm": fm, "text": text,
                          "baseline": y + fm.ascent(),
                          "color": COL[key],
                          "alpha": BASE[key] * dim * (0.92 + 0.08 * breathe)})
            y += fm.height()

        # ---- 4. 横向：长歌词省略号截断 + 换位只在预留的空隙里走 ----
        # 以前长歌词不截断，一长就顶出屏幕左右边缘（也是一种"遮挡"）。
        drift = w * self.TEXT_DRIFT
        max_w = max(40.0, w - 2 * sx - 2 * drift)
        for ln in lines:
            ln["text"] = ln["fm"].elidedText(ln["text"], Qt.ElideRight, int(max_w))
            ln["width"] = ln["fm"].horizontalAdvance(ln["text"])
        block_w = max(ln["width"] for ln in lines)
        slack = max(0.0, (w - 2 * sx - block_w) / 2.0)
        # 横向也走"驻留档位"（0 → 中 → 1 的 smoothstep 循环），而不是正弦。
        # 正弦大部分时间停在振幅中段，摊薄占空比的效果很差；驻留式才会让同一簇字
        # 在几个明确位置上各停一段，像素的平均位置真的变了（和纵向换位同一个道理）。
        # 系数 1.37 让横向周期与纵向换位不成整数倍，二维覆盖图案不会很快重复。
        dx = (self._anchor_pos(t * 1.37 + 51.0) * 2.0 - 1.0) * min(drift, slack)

        return {"style": style, "w": w, "h": h, "band": band,
                "lines": lines,
                # k：自动适配后的字号系数（1.0 = 未缩）。留给调参与诊断看，
                # 不是绘制必需 —— 但少了它排查"时钟怎么变小了"要重新推算。
                "k": k,
                # travel：AOD 换位的实际行程。巡检会断言它没被字号挤成 0 ——
                # 这个盲点曾经真的存在（4 行版式在 16:9 上行程只有 0.1px）。
                "travel": tz_h - block_h,
                "bcx": bcx, "bcy": bcy,
                "cx": w / 2.0 + dx, "breathe": breathe, "dim": dim,
                "block": QRectF(w / 2.0 + dx - block_w / 2.0, block_top, block_w, block_h),
                "tz": QRectF(0.0, tz_top, float(w), tz_h)}

    def _draw_text_block(self, p, plan):
        """按 _plan 算好的基线逐行画文字（水平居中于 cx）"""
        cx = plan["cx"]
        for ln in plan["lines"]:
            a = int(ln["alpha"])
            if a <= 2 or not ln["text"]:
                continue
            c = ln["color"]
            col = QColor(c.red(), c.green(), c.blue(), min(255, a))
            path = QPainterPath()
            path.addText(QPointF(cx - ln["width"] / 2.0, ln["baseline"]), ln["font"], ln["text"])
            p.fillPath(path, col)

    def _draw_bars(self, p, w, h, plan):
        """音浪：底部居中的对称音条，低亮度、缓慢多频起伏，不晕。

        峰高上限取自动画带高度 —— 旧版把峰高写死成 h*0.26、基线 h*0.96，
        峰值时中央几根音条正好顶到上一句歌词上。
        """
        band = plan["band"]
        t = time.monotonic() - self._p_t0
        ar, ag, ab = self.ov.accent1.red(), self.ov.accent1.green(), self.ov.accent1.blue()
        breathe, dim = plan["breathe"], plan["dim"]
        n = 28
        gap = w * 0.010
        bw = (w * 0.82 - gap * (n - 1)) / n
        # 水平跟着整体游移走：音条的**公共基线**本来是一条长期不灭的亮线
        # （实测那些像素占空比 100%），让整排音条横向缓慢迁移才能把它摊开。
        # 竖直方向不动 —— 音浪基线上下晃会立刻显得"画面在抖"。
        x0 = w * 0.09 + (plan["bcx"] - w / 2.0)
        base = band.bottom() - band.height() * 0.06
        max_h = band.height() * 0.80        # 留 20% 顶部余量：峰值也够不到文字
        half = (n - 1) / 2.0
        for i in range(n):
            fi = abs(i - half) / (n / 2.0)          # 0 中心 → 1 边缘
            env = 0.30 + 0.70 * (1.0 - fi)          # 中间高、两边低（左右对称）
            v = 0.55 + 0.45 * math.sin(t * 0.7 + i * 0.45)
            v = v * 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 0.23 + i * 0.9))
            bh = max(2.0, max_h * env * v)
            x = x0 + i * (bw + gap)
            a = int((38 + 80 * (bh / max_h)) * (0.82 + 0.18 * breathe) * dim)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ar, ag, ab, a))
            r = min(bw / 2.0, 5.0)
            p.drawRoundedRect(QRectF(x, base - bh, bw, bh), r, r)

    def _draw_orbits(self, p, w, h, plan):
        """星轨：以动画带中心为圆心的多层同心轨道，各环不同角速度缓慢公转（内外反向）。

        半径上限同时受带高约束 —— 旧版按 min(w,h)*0.34 算，
        16:9 上最外圈压扁后的最低几颗星正好蹭到时钟的头顶。
        """
        band = plan["band"]
        t = time.monotonic() - self._p_t0
        cx, cy = plan["bcx"], plan["bcy"]        # 带游移的中心：星轨圆心不再钉死
        ar, ag, ab = self.ov.accent1.red(), self.ov.accent1.green(), self.ov.accent1.blue()
        dim = plan["dim"]
        # 纵向压扁系数：0.62 的椭圆比正圆更像"轨道"
        FLAT = 0.62
        # 纵向是压扁椭圆，所以 r_max 由「带高一半 ÷ FLAT」反推，再留 6% 余量
        r_max = min(w * 0.42, band.height() * 0.5 / FLAT * 0.94)
        self._fill_band_glow(p, band, ar, ag, ab, 14 * dim)
        c2 = self.ov.accent2
        a2r, a2g, a2b = c2.red(), c2.green(), c2.blue()
        rings = 5
        for ri in range(rings):
            R = (ri + 1) / rings * r_max
            z = (ri + 1) / rings
            speed = (0.10 + ri * 0.05) * (1.0 if ri % 2 == 0 else -1.0)   # 内外反向
            # 极淡的椭圆轨线：让"星轨"读得出轨道来。旧版只有散点，远看像一圈钟面刻度。
            p.setPen(QPen(QColor(ar, ag, ab, max(1, int(7 * z * dim))), 1.0))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, cy), R, R * FLAT)
            # 星数逐环不等，避免各环等分后连成规则"钟面"
            stars = 6 + ri * 3 + (ri * ri) % 4
            for s in range(stars):
                # 黄金角抖动：打散等分感；只跟序号/环号有关，不随时间漂，星点不会乱跳
                jit = 0.34 * math.sin(s * 2.399963 + ri * 1.7)
                ang = 2 * math.pi * s / stars + t * speed + jit
                x = cx + math.cos(ang) * R
                y = cy + math.sin(ang) * R * FLAT
                tw = 0.5 + 0.5 * math.sin(t * 0.30 + s * 1.3 + ri)
                a = int((22 + 74 * z) * (0.74 + 0.26 * tw) * dim)
                # 大小分层：同一环里也有大有小，比"一圈等大点"更像星空
                rr = 0.9 + 2.3 * z * (0.55 + 0.75 * ((s * 5 + ri * 3) % 7) / 6.0)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(a2r, a2g, a2b, a) if (s + ri) % 3 == 0
                           else QColor(ar, ag, ab, a))
                p.drawEllipse(QPointF(x, y), rr, rr)

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        t = time.monotonic() - self._t0

        p.fillRect(0, 0, w, h, QColor(0, 0, 0))     # 纯黑打底（OLED 上黑像素不发光）
        plan = self._plan(w, h, t)

        # 动画先画，并且**裁剪到动画带**：即使动画在数学上画到了带外，
        # 也压不到文字 —— 遮挡在结构上就不可能发生，不依赖参数调得多巧。
        if plan["band"] is not None:
            p.save()
            p.setClipRect(plan["band"])
            if plan["style"] == "particle":
                self._draw_particle_glow(p, w, h, plan)
                self._draw_particles(p, w, h, plan)
            elif plan["style"] == "bars":
                self._draw_bars(p, w, h, plan)
            elif plan["style"] == "orbits":
                self._draw_orbits(p, w, h, plan)
            p.restore()

        self._draw_text_block(p, plan)
        p.end()


class SettingsPanel(QWidget):
    """设置面板：卡片式现代 UI（开关 / 分段选择器 / 字体库 / 屏保 / 系统）"""

    font_prog = Signal(int, int)     # 字体下载进度：(已下载字节, 总字节)
    font_done = Signal(str, object)  # 字体下载完成：(条目 id, 族名列表 或 异常)

    def __init__(self, ov: LyricOverlay):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.ov = ov
        self.setWindowTitle("桌面歌词 · 设置")
        self.setWindowIcon(make_app_icon())
        self.setMinimumWidth(520)
        # 面板本身可获焦：打开时把焦点收在面板上，避免第一个按钮一进来就顶着
        # 焦点描边（看着像"预设选中了某个操作"）。Tab 仍然能在控件间走。
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(548, 760)
        self._accent = QColor(ov.accent1)
        self._switches = []
        self._segs = []
        self._fontrows = {}
        self._dl_id = ""
        self._build()
        self._apply_qss()
        self.refresh()
        self.font_prog.connect(self._on_font_prog)
        self.font_done.connect(self._on_font_done)
        # 打开时的淡入动画
        self._fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(0.0)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.valueChanged.connect(self._fx.setOpacity)
        self._rt = QTimer(self)
        self._rt.timeout.connect(self._refresh_play_state)
        self._rt.start(500)

    def showEvent(self, e):
        super().showEvent(e)
        self._fade.stop()
        self._fade.start()
        # 焦点落在面板本身，而不是自动落到第一个按钮上（否则首个按钮一开面板就带焦点环）
        self.setFocus()

    # ---------- 控件工厂 ----------

    def _switch(self, checked: bool, slot, tip: str = "") -> Switch:
        sw = Switch(checked)
        sw.set_accent(self._accent)
        sw.toggled.connect(slot)
        if tip:
            sw.setToolTip(tip)
        self._switches.append(sw)
        return sw

    def _slider(self, lo: int, hi: int, val: int, slot, w: int = 180) -> QSlider:
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.setFixedWidth(w)
        s.valueChanged.connect(slot)
        return s

    def _val_label(self) -> QLabel:
        lb = QLabel()
        lb.setObjectName("value")
        lb.setFixedWidth(54)
        lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return lb

    # ---------- UI ----------

    def _build(self):
        ov = self.ov
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ===== 顶部标题栏 =====
        head = QWidget()
        head.setObjectName("head")
        head.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(head)
        hl.setContentsMargins(18, 14, 18, 13)
        hl.setSpacing(9)
        tr_ = QHBoxLayout()
        tr_.setSpacing(8)
        title = QLabel("桌面歌词")
        title.setObjectName("title")
        vertag = QLabel("v%s" % APP_VERSION)
        vertag.setObjectName("vertag")
        tr_.addWidget(title)
        tr_.addWidget(vertag)
        tr_.addStretch(1)
        hl.addLayout(tr_)
        self.song_label = QLabel("")
        self.song_label.setObjectName("song")
        hl.addWidget(self.song_label)

        ctl = QHBoxLayout()
        ctl.setSpacing(9)
        self.b_prev = QPushButton()
        self.b_toggle = QPushButton()
        self.b_next = QPushButton()
        self.b_saver = QPushButton()
        self.b_refetch = QPushButton("重新获取歌词")
        self.b_refetch.setObjectName("ghost")
        self.b_refetch.setCursor(Qt.PointingHandCursor)
        for b, tip, obj, ic, sz in ((self.b_prev, "上一首", "ctl", "prev", 19),
                                    (self.b_toggle, "播放 / 暂停", "ctlplay", "play", 30),
                                    (self.b_next, "下一首", "ctl", "next", 19),
                                    (self.b_saver, "氛围屏保", "ctl", "saver", 19)):
            b.setToolTip(tip)
            b.setObjectName(obj)
            b.setCursor(Qt.PointingHandCursor)
            if obj == "ctlplay":
                b.setIcon(make_play_icon(bg=self._accent, glyph="play"))
            else:
                b.setIcon(make_media_icon(ic))
            b.setIconSize(QSize(sz, sz))
            ctl.addWidget(b)
        self.b_prev.clicked.connect(lambda: ov.media_command("prev"))
        self.b_toggle.clicked.connect(lambda: ov.media_command("toggle"))
        self.b_next.clicked.connect(lambda: ov.media_command("next"))
        self.b_saver.clicked.connect(lambda: ov.open_saver())
        self.b_refetch.clicked.connect(ov._refresh_lyrics)
        ctl.addStretch(1)
        ctl.addWidget(self.b_refetch)
        hl.addLayout(ctl)
        root.addWidget(head)

        # ===== 滚动内容区 =====
        scroll = QScrollArea()
        scroll.setObjectName("scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("content")
        cv = QVBoxLayout(content)
        cv.setContentsMargins(14, 12, 14, 14)
        cv.setSpacing(11)
        scroll.setWidget(content)
        self._content = content
        root.addWidget(scroll, 1)

        # ---- 歌词同步 ----
        c1, l1 = make_card("歌词同步")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.off_slider = self._slider(-10, 10, int(round(ov.offset / 0.5)), self._on_offset, 200)
        self.off_label = self._val_label()
        row.addWidget(self.off_slider)
        row.addStretch(1)
        row.addWidget(self.off_label)
        l1.addLayout(row)
        hb = QHBoxLayout()
        hb.setSpacing(8)
        for text, delta in (("提前 0.5s", 5), ("延后 0.5s", -5), ("归零", None)):
            btn = QPushButton(text)
            if delta is None:
                btn.clicked.connect(lambda: self.off_slider.setValue(0))
            else:
                btn.clicked.connect(
                    lambda _=False, d=delta: self.off_slider.setValue(self.off_slider.value() + d))
            hb.addWidget(btn)
        hb.addStretch(1)
        l1.addLayout(hb)
        hint = QLabel("歌词比歌声慢 → 点「提前」；比歌声快 → 点「延后」。正值为提前。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        l1.addWidget(hint)
        cv.addWidget(c1)

        # ---- 外观 ----
        c2, l2 = make_card("外观")
        self.style_combo = QComboBox()
        for key, name in STYLE_NAMES.items():
            self.style_combo.addItem(name, key)
        i = self.style_combo.findData(ov.style_mode)
        if i >= 0:
            self.style_combo.setCurrentIndex(i)
        self.style_combo.currentIndexChanged.connect(self._on_style)
        l2.addWidget(make_row("悬浮样式", self.style_combo))

        self.font_combo = QComboBox()
        self.font_combo.setMinimumWidth(230)
        self._rebuild_font_combo()
        self.font_combo.currentIndexChanged.connect(self._on_font)
        l2.addWidget(make_row("字体", self.font_combo, hint="字体库字体 / 系统字体"))

        self.scale_slider = self._slider(6, 18, int(round(ov.font_scale * 10)), self._on_scale)
        self.scale_label = self._val_label()
        l2.addWidget(make_row("字号", self.scale_slider, self.scale_label))

        self.op_slider = self._slider(3, 10, int(round(ov.opacity * 10)), self._on_opacity)
        self.op_label = self._val_label()
        l2.addWidget(make_row("透明度", self.op_slider, self.op_label))

        self.anim_combo = QComboBox()
        for key, name in ANIM_STYLES.items():
            self.anim_combo.addItem(name, key)
        i = self.anim_combo.findData(ov.anim_style)
        if i >= 0:
            self.anim_combo.setCurrentIndex(i)
        self.anim_combo.currentIndexChanged.connect(self._on_anim)
        l2.addWidget(make_row("逐字动画", self.anim_combo))

        self.fade_slider = self._slider(0, 6, int(round(ov.edge_fade_px / 10.0)), self._on_fade, 120)
        self.fade_check = self._switch(ov.edge_fade, self._on_fade)
        l2.addWidget(make_row("边缘虚化", self.fade_slider, self.fade_check))

        self.dm_seg = Segmented([("desktop", "常驻桌面"), ("topmost", "置顶悬浮")],
                                ov.display_mode, h=32)
        self.dm_seg.set_accent(self._accent)
        self.dm_seg.changed.connect(self._on_display_seg)
        self._segs.append(self.dm_seg)
        l2.addWidget(make_row("显示模式", self.dm_seg))

        self.cover_check = self._switch(ov.show_cover, ov.set_show_cover)
        self.trans_check = self._switch(ov.show_trans, ov.set_show_trans)
        self.time_check = self._switch(ov.show_time, ov.set_show_time)
        g2 = QGridLayout()
        g2.setHorizontalSpacing(16)
        g2.setVerticalSpacing(8)
        g2.addWidget(make_row("专辑封面", self.cover_check), 0, 0)
        g2.addWidget(make_row("翻译歌词", self.trans_check), 0, 1)
        g2.addWidget(make_row("进度时间", self.time_check), 1, 0)
        l2.addLayout(g2)
        cv.addWidget(c2)

        # ---- 字体库 ----
        c3, l3 = make_card("字体库 · 免费商用一键下载")
        tip3 = QLabel("下载后自动装入并立即生效；字体保存在 %APPDATA%\\Desktop-sing\\fonts，"
                      "非系统字体也能用，不局限于电脑自带字体。")
        tip3.setObjectName("hint")
        tip3.setWordWrap(True)
        l3.addWidget(tip3)
        for ent in FONT_LIBRARY:
            roww = QWidget()
            rowl = QHBoxLayout(roww)
            rowl.setContentsMargins(0, 2, 0, 2)
            rowl.setSpacing(10)
            col = QVBoxLayout()
            col.setSpacing(1)
            nm = QLabel("%s   ·   %.1f MB" % (ent["name"], ent["mb"]))
            nm.setObjectName("fontname")
            nt = QLabel(ent["note"])
            nt.setObjectName("fontnote")
            nt.setWordWrap(True)
            col.addWidget(nm)
            col.addWidget(nt)
            rowl.addLayout(col, 1)
            btn = QPushButton("下载")
            btn.setObjectName("dl")
            btn.setFixedWidth(92)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, e=ent: self._on_font_action(e))
            rowl.addWidget(btn)
            self._fontrows[ent["id"]] = (btn, nm)
            l3.addWidget(roww)
        self.font_status = QLabel("")
        self.font_status.setObjectName("hint")
        self.font_status.setWordWrap(True)
        l3.addWidget(self.font_status)
        cv.addWidget(c3)

        # ---- 悬浮窗 ----
        c4, l4 = make_card("悬浮窗")
        self.glow_check = self._switch(ov.glow, ov.set_glow)
        self.pfade_check = self._switch(ov.pause_fade, ov.set_pause_fade)
        self.lock_check = self._switch(ov.locked, ov.set_locked)
        self.ct_check = self._switch(ov.click_through, ov.set_click_through)
        g4 = QGridLayout()
        g4.setHorizontalSpacing(16)
        g4.setVerticalSpacing(8)
        g4.addWidget(make_row("氛围光晕", self.glow_check), 0, 0)
        g4.addWidget(make_row("暂停淡出", self.pfade_check), 0, 1)
        g4.addWidget(make_row("锁定位置", self.lock_check), 1, 0)
        g4.addWidget(make_row("点击穿透", self.ct_check), 1, 1)
        l4.addLayout(g4)
        hb4 = QHBoxLayout()
        hb4.setSpacing(8)
        b_reset = QPushButton("重置位置")
        b_reset.clicked.connect(ov._reset_position)
        b_test = QPushButton("预览屏保")
        b_test.clicked.connect(lambda: ov.open_saver())
        hb4.addWidget(b_reset)
        hb4.addWidget(b_test)
        hb4.addStretch(1)
        l4.addLayout(hb4)
        cv.addWidget(c4)

        # ---- 氛围屏保 ----
        c5, l5 = make_card("氛围屏保 · 黑底防烧屏")
        self.saver_check = self._switch(ov.idle_saver, ov.set_idle_saver)
        l5.addWidget(make_row("空闲自动进入", self.saver_check))
        self.idle_combo = QComboBox()
        for m in (3, 5, 10, 15, 20, 30, 45, 60):
            self.idle_combo.addItem("%d 分钟" % m, m)
        i = self.idle_combo.findData(ov.idle_min)
        if i >= 0:
            self.idle_combo.setCurrentIndex(i)
        self.idle_combo.currentIndexChanged.connect(self._on_idle_min)
        l5.addWidget(make_row("空闲阈值", self.idle_combo))
        self.saver_idle_check = self._switch(ov.saver_idle_only, ov.set_saver_idle_only)
        l5.addWidget(make_row("仅空闲时自动启动", self.saver_idle_check))
        self.saver_seg = Segmented([("particle", "3D 粒子"), ("minimal", "极简"),
                                    ("bars", "音浪"), ("orbits", "星轨")],
                                   ov.saver_style, h=30)
        self.saver_seg.set_accent(self._accent)
        self.saver_seg.changed.connect(self._on_saver_style)
        self._segs.append(self.saver_seg)
        l5.addWidget(make_row("屏保风格", self.saver_seg))
        # 当前风格的实时预览缩略图（点击可立即进入屏保）——给切换一个即时可见的反馈
        self.saver_preview = QLabel()
        self.saver_preview.setObjectName("saverpreview")
        self.saver_preview.setFixedSize(252, 142)
        self.saver_preview.setAlignment(Qt.AlignCenter)
        self.saver_preview.setStyleSheet("border-radius:10px;background:#000;")
        self.saver_preview.setCursor(Qt.PointingHandCursor)
        self.saver_preview.setToolTip("当前选择的屏保风格预览（点击可立即进入屏保）")
        self.saver_preview.mousePressEvent = lambda _e: ov.open_saver()
        l5.addWidget(self.saver_preview)
        h5 = QLabel("3D 粒子 = 星云随乐缓缓流转；极简 = 纯黑 + 大时钟；"
                    "音浪 = 底部居中的对称音条；星轨 = 同心圆星轨公转。"
                    "四种都极慢、低亮度、居中对称，适合写作业/挂机当氛围感，长时间也不烧屏。"
                    "系统锁屏期间不重复启动，按任意键或点一下鼠标即可退出。")
        h5.setObjectName("hint")
        h5.setWordWrap(True)
        l5.addWidget(h5)
        b_saver = QPushButton("立即进入屏保")
        b_saver.setObjectName("saver")
        b_saver.setCursor(Qt.PointingHandCursor)
        b_saver.clicked.connect(lambda: ov.open_saver())
        l5.addWidget(b_saver)
        cv.addWidget(c5)

        # ---- 系统 ----
        c6, l6 = make_card("系统")
        self.auto_check = self._switch(autostart_enabled(), self._on_autostart)
        l6.addWidget(make_row("开机自启", self.auto_check, hint="随登录启动"))
        self.keep_check = self._switch(ov.keepalive, ov.set_keepalive)
        l6.addWidget(make_row("进程保活", self.keep_check, hint="崩溃自动拉起"))
        self.hk_check = self._switch(ov.hotkeys_on, ov.set_hotkeys)
        l6.addWidget(make_row("全局快捷键", self.hk_check, hint="默认关闭"))

        # ---- 更新 ----
        self.update_url_edit = QLineEdit()
        self.update_url_edit.setPlaceholderText("留空 = 内置源（GitHub 查版本 + 蓝奏云镜像下载）")
        self.update_url_edit.setText((ov.cfg.get("update_url") or "").strip())
        self.update_url_edit.setMinimumWidth(280)
        self.update_url_edit.editingFinished.connect(self._on_update_url)
        l6.addWidget(make_row("更新地址", self.update_url_edit, hint="留空即用内置源"))
        self.update_auto_check = self._switch(ov.update_auto, self._on_update_auto)
        l6.addWidget(make_row("启动自动检查", self.update_auto_check,
                              hint="上传新版本后自动提示"))
        self.update_check_btn = QPushButton("立即检查更新")
        self.update_check_btn.setObjectName("ghost")
        self.update_check_btn.setCursor(Qt.PointingHandCursor)
        self.update_check_btn.clicked.connect(lambda: ov.check_update(manual=True))
        l6.addWidget(self.update_check_btn)
        upd_tip = QLabel("内置更新源：GitHub / Gitee 查版本号 · 下载默认走蓝奏云镜像（国内更快）")
        upd_tip.setObjectName("rowhint")
        upd_tip.setWordWrap(True)
        l6.addWidget(upd_tip)

        keys_box = QWidget()
        keys_box.setObjectName("keys")
        keys_box.setAttribute(Qt.WA_StyledBackground, True)
        kb = QGridLayout(keys_box)
        kb.setContentsMargins(12, 9, 12, 9)
        kb.setHorizontalSpacing(16)
        kb.setVerticalSpacing(4)
        for i, (_a, desc, combo, _m, _v) in enumerate(HOTKEY_DEFS):
            lb = QLabel("%s   %s" % (combo, desc))
            lb.setObjectName("keyitem")
            kb.addWidget(lb, i // 2, i % 2)
        l6.addWidget(keys_box)
        cv.addWidget(c6)

        cv.addStretch(1)
        foot = QLabel("桌面歌词 v%s · 本地运行，不上传任何数据" % APP_VERSION)
        foot.setObjectName("footer")
        foot.setAlignment(Qt.AlignCenter)
        cv.addWidget(foot)

        # 面板里所有下拉框统一修一次弹层白边（原因见 fix_combo_popup 的注释）
        for cb in self.findChildren(QComboBox):
            fix_combo_popup(cb)

    # ---------- 字体库 ----------

    def _rebuild_font_combo(self):
        ov = self.ov
        self.font_combo.blockSignals(True)
        self.font_combo.clear()
        self.font_combo.addItem("默认（MiSans / 雅黑）", "")
        for fam in LOADED_FAMILIES:                       # 字体库（已下载 / 自带）
            self.font_combo.addItem("%s   · 字体库" % fam, fam)
        sys_fams = set(QFontDatabase.families())
        for fam in CURATED_FONTS:                         # 系统已装精选
            if fam in sys_fams and self.font_combo.findData(fam) < 0:
                self.font_combo.addItem(fam, fam)
        if ov.font_family and self.font_combo.findData(ov.font_family) < 0:
            self.font_combo.addItem(ov.font_family, ov.font_family)   # 保留历史选择
        j = self.font_combo.findData(ov.font_family or "")
        if j >= 0:
            self.font_combo.setCurrentIndex(j)
        self.font_combo.blockSignals(False)

    def _on_font_action(self, ent: dict):
        """字体库按钮：未装 → 下载；已装 → 直接使用"""
        if font_library_state().get(ent["id"]):
            fams = [f for f in LOADED_FAMILIES if _font_family_match(f, ent["id"])]
            if not fams:
                _load_fonts()
                fams = [f for f in LOADED_FAMILIES if _font_family_match(f, ent["id"])]
            fam = _pick_family(fams)
            if fam:
                self.ov.set_font_family(fam)
                self._rebuild_font_combo()
                self._sync_fontlib()
                self.font_status.setText("已切换到「%s」" % fam)
            return
        if self._dl_id:
            return
        self._dl_id = ent["id"]
        btn = self._fontrows[ent["id"]][0]
        btn.setEnabled(False)
        btn.setText("0%")
        self.font_status.setText("正在下载「%s」…" % ent["name"])

        def prog(done, total):
            self.font_prog.emit(done, total)

        def work():
            try:
                self.font_done.emit(ent["id"], download_font(ent, on_progress=prog))
            except Exception as ex:      # 网络失败不崩面板，回主线程提示
                self.font_done.emit(ent["id"], ex)

        threading.Thread(target=work, daemon=True).start()

    def _on_font_prog(self, done: int, total: int):
        if not self._dl_id:
            return
        btn = self._fontrows[self._dl_id][0]
        if total > 0:
            btn.setText("%d%%" % int(done * 100 / total))
        else:
            btn.setText("%.1fM" % (done / 1048576.0))

    def _on_font_done(self, eid: str, result):
        self._dl_id = ""
        btn = self._fontrows[eid][0]
        btn.setEnabled(True)
        if isinstance(result, Exception) or not result:
            btn.setText("重试")
            self.font_status.setText("字体下载失败，请检查网络后重试。")
            return
        _load_fonts()                                    # 重新扫描并加载
        self._rebuild_font_combo()
        fam = _pick_family([f for f in result if f] or
                           [f for f in LOADED_FAMILIES if _font_family_match(f, eid)])
        if fam:
            self.ov.set_font_family(fam)
            self._rebuild_font_combo()
            j = self.font_combo.findData(fam)
            if j >= 0:
                self.font_combo.blockSignals(True)
                self.font_combo.setCurrentIndex(j)
                self.font_combo.blockSignals(False)
            self.font_status.setText("已下载并启用「%s」" % fam)
        else:
            self.font_status.setText("字体已下载，可用字体列表里选择。")
        self._sync_fontlib()

    def _sync_fontlib(self):
        """按「已装 / 使用中」刷新字体库按钮的文字与配色"""
        state = font_library_state()
        cur = self.ov.font_family or ""
        for ent in FONT_LIBRARY:
            btn, _nm = self._fontrows[ent["id"]]
            if not state.get(ent["id"]):
                btn.setText("下载 %.0fM" % ent["mb"])
                obj = "dl"
            else:
                fam = _pick_family([f for f in LOADED_FAMILIES
                                    if _font_family_match(f, ent["id"])])
                if fam and fam == cur:
                    btn.setText("使用中")
                    obj = "dlon"
                else:
                    btn.setText("使用")
                    obj = "dluse"
            if btn.objectName() != obj:
                btn.setObjectName(obj)
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    # ---------- 槽 ----------

    def _on_offset(self, v):
        self.ov.set_offset(v * 0.5)
        self.off_label.setText("%+.1fs" % (v * 0.5))

    def _on_font(self, i):
        self.ov.set_font_family(self.font_combo.itemData(i) or "")
        self._sync_fontlib()

    def _on_scale(self, v):
        self.ov.set_font_scale(v / 10.0)
        self.scale_label.setText("%d%%" % (v * 10))

    def _on_opacity(self, v):
        self.ov.set_opacity(v / 10.0)
        self.op_label.setText("%d%%" % (v * 10))

    def _on_anim(self, i):
        k = self.anim_combo.itemData(i)
        if k:
            self.ov.set_anim_style(k)

    def _on_style(self, i):
        k = self.style_combo.itemData(i)
        if k:
            self.ov.set_style_mode(k)

    def _on_display_seg(self, key):
        self.ov.set_display_mode(key)

    def _on_fade(self, *_):
        self.ov.set_edge_fade(self.fade_check.isChecked(), self.fade_slider.value() * 10)

    def _on_idle_min(self, i):
        self.ov.set_idle_min(self.idle_combo.itemData(i))

    def _on_saver_style(self, key):
        self.ov.set_saver_style(key)
        self._update_saver_preview()

    def _update_saver_preview(self):
        """把当前屏保风格渲染成小预览图，给面板里的切换提供即时可见反馈"""
        ov = self.ov
        s = AmbientSaver(ov)
        s._timer.stop()                 # 只取一帧静态预览，不启动动画定时器
        w, h = 252, 142
        s.resize(w, h)
        pm = QPixmap(w, h)
        pm.fill(QColor(0, 0, 0))
        s.render(pm)
        pm = round_pixmap(pm, 10)       # QLabel 的 border-radius 不裁子级 pixmap，得自己圆
        self.saver_preview.setPixmap(
            pm.scaled(self.saver_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        s.deleteLater()

    def _on_autostart(self, on):
        if not set_autostart(bool(on)):
            self.auto_check.setChecked(not on, animate=True)   # 写注册表失败则回弹
        else:
            self.ov.tray.showMessage("桌面歌词", "已%s开机自启" % ("开启" if on else "关闭"),
                                     QSystemTrayIcon.Information, 1500)

    def _on_update_url(self):
        self.ov.set_update_url(self.update_url_edit.text().strip())

    def _on_update_auto(self, on):
        self.ov.set_update_auto(bool(on))

    # ---------- 刷新 / 换肤 ----------

    def refresh(self):
        """从 overlay 重新同步（面板外改动后调用）"""
        ov = self.ov
        for sl, val, lb, txt in (
                (self.off_slider, int(round(ov.offset / 0.5)), self.off_label, "%+.1fs" % ov.offset),
                (self.scale_slider, int(round(ov.font_scale * 10)), self.scale_label,
                 "%d%%" % int(round(ov.font_scale * 100))),
                (self.op_slider, int(round(ov.opacity * 10)), self.op_label,
                 "%d%%" % int(round(ov.opacity * 100)))):
            sl.blockSignals(True)
            sl.setValue(val)
            sl.blockSignals(False)
            lb.setText(txt)
        for combo, key in ((self.anim_combo, ov.anim_style),
                           (self.style_combo, ov.style_mode)):
            i = combo.findData(key)
            if i >= 0 and combo.currentIndex() != i:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)
        j = self.font_combo.findData(ov.font_family or "")
        if j >= 0 and self.font_combo.currentIndex() != j:
            self.font_combo.blockSignals(True)
            self.font_combo.setCurrentIndex(j)
            self.font_combo.blockSignals(False)
        self.fade_check.blockSignals(True)
        self.fade_check.setChecked(ov.edge_fade)
        self.fade_check.blockSignals(False)
        self.fade_slider.blockSignals(True)
        self.fade_slider.setValue(int(round(ov.edge_fade_px / 10.0)))
        self.fade_slider.blockSignals(False)
        self.dm_seg.setValue(ov.display_mode, animate=False)
        self.saver_seg.setValue(ov.saver_style, animate=False)
        self._update_saver_preview()
        i = self.idle_combo.findData(ov.idle_min)
        if i < 0:
            i = 0
        self.idle_combo.blockSignals(True)
        self.idle_combo.setCurrentIndex(i)
        self.idle_combo.blockSignals(False)
        for chk, val in ((self.cover_check, ov.show_cover),
                         (self.trans_check, ov.show_trans),
                         (self.time_check, ov.show_time),
                         (self.glow_check, ov.glow),
                         (self.pfade_check, ov.pause_fade),
                         (self.lock_check, ov.locked),
                         (self.ct_check, ov.click_through),
                         (self.hk_check, ov.hotkeys_on),
                         (self.keep_check, ov.keepalive),
                         (self.saver_check, ov.idle_saver),
                         (self.saver_idle_check, ov.saver_idle_only),
                         (self.auto_check, autostart_enabled())):
            chk.blockSignals(True)
            chk.setChecked(val)
            chk.blockSignals(False)
        self._sync_fontlib()
        self._refresh_play_state()

    def _refresh_play_state(self):
        if self.ov.song:
            t = self.ov._title_text()
            if self.ov.status != "PLAYING":
                t += "（已暂停）"
        else:
            t = "等待播放…在 QQ音乐 / 网易云 / Spotify 播放歌曲即可显示歌词"
        self.song_label.setText(t)
        self.b_toggle.setIcon(make_play_icon(
            bg=self._accent,
            glyph="pause" if self.ov.status == "PLAYING" else "play"))

    def update_accent(self, accent: QColor):
        self._accent = QColor(accent)
        for sw in self._switches:
            sw.set_accent(self._accent)
        for sg in self._segs:
            sg.set_accent(self._accent)
        self._apply_qss()
        self._refresh_play_state()

    def _apply_qss(self):
        a = self._accent.name()
        al = self._accent.lighter(132).name()     # 主色提亮：按钮 / 进度条的渐变顶色
        arrow = combo_arrow_url()
        arrow_rule = ("QComboBox::down-arrow { image: url(%s); width: 12px; height: 12px; }\n"
                      "        QComboBox::down-arrow:on { image: url(%s); }" % (arrow, arrow)) \
            if arrow else "QComboBox::down-arrow { image: none; width: 0; height: 0; }"
        qss = """
        QWidget { background: transparent; color: #dfe4ee; font-size: 13px;
                  font-family: "Microsoft YaHei UI"; }
        /* 头部比内容区略亮一档 + 下边缘一条落影线：滚动内容往上顶时能读出层次 */
        QWidget#head { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #181c24, stop:1 #12151b);
                       border-bottom: 1px solid rgba(0,0,0,130); }
        QWidget#content { background: #0f1116; }
        QScrollArea#scroll { background: #0f1116; border: none; }
        QScrollArea#scroll > QWidget > QWidget { background: #0f1116; }
        QScrollBar:vertical { background: transparent; width: 10px; margin: 3px 2px; }
        QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 5px;
                                      min-height: 38px; }
        QScrollBar::handle:vertical:hover { background: rgba(255,255,255,86); }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        QLabel#title { color: #f2f5fa; font-size: 19px; font-weight: 700; }
        QLabel#vertag { color: #7f8798; font-size: 11px; padding: 2px 7px;
                        border: 1px solid rgba(255,255,255,26); border-radius: 8px; }
        QLabel#song  { color: #98a0b2; font-size: 12px; }
        QLabel#hint  { color: #79808f; font-size: 12px; }
        QLabel#footer { color: #6b7280; font-size: 11px; padding: 4px 0 2px 0; }
        QLabel#value { color: #cfd6e4; font-size: 12px; }
        QLabel#rowlabel { color: #c6cddb; font-size: 13px; }
        QLabel#rowhint { color: #6f7787; font-size: 11px; }
        /* 分区标题：主色文字 + 左侧 3px 主色小竖条。比单纯染色更容易一眼定位分区，
           竖条也把标题和卡片左内边距对齐成一条视觉轴。 */
        QLabel#cardtitle { color: __A__; font-size: 12px; font-weight: 700;
                           letter-spacing: 1px;
                           border-left: 3px solid __A__;
                           padding-left: 8px; padding-top: 1px; padding-bottom: 1px; }
        QLabel#fontname { color: #d6dbe6; font-size: 13px; font-weight: 600; }
        QLabel#fontnote { color: #7d8595; font-size: 11px; }
        /* 卡片：顶部一条受光带 + 上亮下暗的分层描边。原来只有一层平描边 + 微渐变，
           读起来还是"贴在面板上的一张色纸"；补上「上缘接光 / 下缘落影」之后，
           它才成为一块"微微抬起的板"。 */
        QWidget#card { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0    __CARD_TOP__,
                                                   stop:0.04 __CARD_BODY__,
                                                   stop:1    __CARD_BOT__);
                       border: 1px solid __MID__;
                       border-top-color: __HI__;
                       border-bottom-color: __LO__;
                       border-radius: __R_CARD__px; }
        /* 快捷键表做成「凹槽」（比卡片更深、上暗下亮），与"凸起"的卡片形成对照 */
        QWidget#keys { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                   stop:0 #0d1015, stop:1 #141821);
                       border: 1px solid __MID__;
                       border-top-color: __LO__;
                       border-bottom-color: rgba(255,255,255,26);
                       border-radius: 10px; }
        QLabel#keyitem { color: #96a0b3; font-size: 12px; font-family: "Consolas", monospace; }
        QComboBox { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                stop:0 __CTRL_TOP__, stop:1 __CTRL_BOT__);
                    border: 1px solid __MID__;
                    border-top-color: __HI__;
                    border-radius: __R_CTRL__px; padding: 5px 10px; min-height: 16px; }
        QComboBox:hover { border-color: __A__; border-top-color: __A__; }
        QComboBox::drop-down { border: none; width: 22px; }
        __ARROW__
        /* 下拉弹层是独立的弹出窗口，不会继承面板的内边距，得自己给 ——
           否则选项会紧贴边框，和已经打磨过的菜单观感对不上。 */
        QComboBox QAbstractItemView { background: #1e222b; color: #dfe4ee; outline: none;
                                      border: 1px solid rgba(255,255,255,24);
                                      border-radius: 8px; padding: 5px;
                                      selection-background-color: __A__;
                                      selection-color: #10131a; }
        QComboBox QAbstractItemView::item { padding: 6px 10px; border-radius: 6px;
                                            min-height: 18px; }
        /* 按钮：默认态顶部接光；按下态把受光方向反转（顶部变暗）= "被按进去"。
           原来按下只是换了个更亮的底色，方向是反的（按下去反而更亮），读着别扭。 */
        QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                  stop:0 __CTRL_TOP__, stop:1 __CTRL_BOT__);
                      border: 1px solid __MID__;
                      border-top-color: __HI__;
                      border-radius: __R_CTRL__px; padding: 6px 12px; color: #e6ebf4; }
        QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                        stop:0 #2f3542, stop:1 #21262f);
                            border-color: __A__; border-top-color: __A__; color: #ffffff; }
        QPushButton:pressed { background: #171a21;
                              border-color: __MID__; border-top-color: rgba(255,255,255,10); }
        /* 键盘 Tab 到按钮时给个描边反馈；边框宽度不变，所以不会有布局跳动 */
        QPushButton:focus { border-color: __A__; border-top-color: __A__; }
        QPushButton:disabled { color: #6b7280; border-color: rgba(255,255,255,14); }
        /* 头部控制键：软图标按钮——去掉硬边框感（半透明填充 + 大圆角），
           和下面卡片的圆润语言对齐。原来是棱角分明的方盒，像系统默认控件。 */
        QPushButton#ctl { padding: 6px 11px; min-width: 30px;
                          border-radius: __R_ICON__px;
                          background: rgba(255,255,255,11);
                          border: 1px solid rgba(255,255,255,18);
                          border-top-color: rgba(255,255,255,30); }
        QPushButton#ctl:hover { background: rgba(255,255,255,22);
                                border-color: rgba(255,255,255,34);
                                border-top-color: rgba(255,255,255,50); }
        QPushButton#ctl:pressed { background: rgba(255,255,255,7);
                                  border-top-color: rgba(255,255,255,12); }
        QPushButton#ctlplay { padding: 2px; border: none; background: transparent;
                              border-radius: 17px; }
        QPushButton#ctlplay:hover { background: rgba(255,255,255,20); }
        QPushButton#ghost { background: transparent; color: #98a0b2; }
        QPushButton#ghost:hover { color: __A__; border-color: __A__; }
        QPushButton#primary { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                          stop:0 __AL__, stop:1 __A__);
                              color: #10131a; border: none;
                              font-weight: 700; padding: 8px 12px; }
        QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                                stop:0 #ffffff, stop:1 #eef1f7);
                                    color: #10131a; }
        QPushButton#primary:pressed { background: __A__; color: #10131a; }
        /* 屏保入口：原先是通栏高饱和主色按钮，视觉上像"危险操作"。屏保本身只是个
           可逆的展示态（上方缩略图也能点进去），降级成描边式操作更贴合"精致柔和"。 */
        QPushButton#saver { background: rgba(255,255,255,9); color: __A__;
                            border: 1px solid __A__; border-radius: 10px;
                            font-weight: 600; padding: 9px 12px; }
        QPushButton#saver:hover { background: __A__; color: #10131a; }
        QPushButton#saver:pressed { background: __A__; color: #10131a; }
        QPushButton#dl { background: transparent; color: __A__; border: 1px solid __A__;
                         padding: 5px 8px; font-size: 12px; }
        QPushButton#dl:hover { background: __A__; color: #10131a; }
        QPushButton#dluse { background: transparent; color: #9aa3b5;
                            border: 1px solid rgba(255,255,255,30); padding: 5px 8px;
                            font-size: 12px; }
        QPushButton#dluse:hover { color: #fff; border-color: __A__; }
        QPushButton#dlon { background: rgba(120,130,150,60); color: #cfd6e4; border: none;
                           padding: 5px 8px; font-size: 12px; }
        QPushButton#dl:disabled, QPushButton#dlon:disabled { color: #8b93a5; }
        /* 轨道做成凹槽（顶部更暗）；滑块白钮加一圈 1px 暗环——白钮在亮卡片 / 浅色壁纸上
           没有环会"糊"进背景，加环才有边界。 */
        QSlider::groove:horizontal { height: 6px; border-radius: 3px;
                                     background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                                 stop:0 __GROOVE__, stop:1 #191d26); }
        QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                                   stop:0 __AL__, stop:1 __A__);
                                       border-radius: 3px; }
        /* 圆钮：15px 配 radius 8 在 Qt 里会渲染成圆角方块，14px 配 radius 7 才是正圆 */
        QSlider::handle:horizontal { width: 14px; height: 14px; margin: -4px 0;
                                     border-radius: 7px; background: #f2f6fc;
                                     border: 1px solid rgba(0,0,0,70); }
        QSlider::handle:horizontal:hover { background: #ffffff; border-color: rgba(0,0,0,95); }
        QToolTip { background: #1e222b; color: #dfe4ee; border: 1px solid rgba(255,255,255,30);
                   padding: 4px 6px; }
        """
        # 令牌 → 占位符一次替换。集中替换而不是各写各的，是为了让「光从上方来」这套
        # 假设在面板/控件/菜单里永远是同一组数值（见文件顶部 UI_* 令牌）。
        toks = {
            "__R_CARD__": str(UI_R_CARD), "__R_CTRL__": str(UI_R_CTRL),
            "__R_ICON__": str(UI_R_ICONBTN), "__GROOVE__": UI_GROOVE,
            "__CARD_TOP__": UI_CARD_TOP, "__CARD_BODY__": UI_CARD_BODY,
            "__CARD_BOT__": UI_CARD_BOT, "__CTRL_TOP__": UI_CTRL_TOP,
            "__CTRL_BOT__": UI_CTRL_BOT, "__HI__": UI_EDGE_HI,
            "__LO__": UI_EDGE_LO, "__MID__": UI_EDGE_MID,
            "__AL__": al, "__A__": a, "__ARROW__": arrow_rule,
        }
        for k, v in toks.items():
            qss = qss.replace(k, v)
        self.setStyleSheet(qss)

def _request_takeover(timeout: float = 8.0) -> bool:
    """写接管哨兵请求旧实例退出，并轮询等它真的关掉（升级替换时使用）

    旧实例在主循环里发现 restart.sig 就正常退出（含停机哨兵，守护进程不会复活它）。
    返回 True = 旧实例已让位，可以继续启动。
    """
    try:
        with open(RESTART_SIG, "w", encoding="utf-8") as f:
            f.write("ver=%s\npid=%d\nts=%d" % (APP_VERSION, os.getpid(), int(time.time())))
    except OSError:
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.25)
        s = QLocalSocket()
        s.connectToServer(APP_NAME)
        alive = s.waitForConnected(200)
        s.abort()
        if not alive:
            try:
                if os.path.exists(RESTART_SIG):
                    os.remove(RESTART_SIG)
            except OSError:
                pass
            return True
    return False


def _selftest() -> int:
    """打包后自检：验证运行时依赖（winsdk / Qt / 字体 / 5 种样式渲染）是否齐全。

    用法：Desktop-sing.exe --selftest
    结果同时写日志（%APPDATA%\\Desktop-sing\\desktop-lyrics.log），无控制台也能看。
    注意：这里不调用任何会写配置的 setter，也不会拉起守护进程，避免污染用户设置。
    """
    import asyncio
    os.environ[SUPERVISED_ENV] = "1"        # 抑制守护进程拉起
    # 结果单独落一份文件：无控制台打包下日志是唯一出口，但不能连日志都写不出来
    _st = [os.path.join(CFG_DIR, "selftest.txt")]

    def _mark(line):
        try:
            with open(_st[0], "a", encoding="utf-8") as f:
                f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), line))
        except OSError:
            pass

    try:
        with open(_st[0], "w", encoding="utf-8") as f:
            f.write("selftest v%s %s\n" % (APP_VERSION, time.strftime("%Y-%m-%d %H:%M:%S")))
    except OSError:
        pass
    _mark("start")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("桌面歌词")
    app.setApplicationVersion(APP_VERSION)
    _mark("qt ok")

    res = []
    try:
        async def _probe():
            # winsdk 返回的是 IAsyncOperation（不是 coroutine），必须在 async 函数里 await
            if not _load_smtc():
                raise RuntimeError("SMTC 绑定缺失（winsdk / winrt 未安装）")
            mgr = await MediaManager.request_async()
            sessions = mgr.get_sessions() or []
            names = []
            for s in sessions:                  # 读属性触发 WinRT 类型解析，顺带验证裁剪
                try:
                    prop = await s.try_get_media_properties_async()
                    names.append(prop.title or "?")
                except Exception:
                    names.append("<read fail>")
            return len(sessions), names

        n, names = asyncio.run(_probe())
        res.append("SMTC ok (sessions=%d%s)" % (n, (": " + ", ".join(names)) if names else ""))
    except Exception:
        res.append("SMTC FAIL: " + (traceback.format_exc().strip().splitlines()[-1]))
    _mark(res[-1])

    try:
        _load_fonts()
        res.append("fonts ok")
    except Exception:
        res.append("fonts FAIL: " + (traceback.format_exc().strip().splitlines()[-1]))

    try:
        ov = LyricOverlay(MediaWatcher())
        ov.song = {"title": "自检", "artist": "selftest", "source": "qq", "cover": None}
        ov.lines = [[0.0, "第一句"], [3.0, "自检歌词一行"], [9.0, "末句"]]
        ov.words = {1: [(3.0, 1.5, "自检歌词"), (4.5, 1.5, "一行")]}
        ov.status = "PLAYING"
        ov.cur_idx = 1
        ov._current_text = "自检歌词一行"
        ov._next_text = "末句"
        ov._line_t = 1.0
        ov.anchor_pos = 4.0
        ov.anchor_ts = time.monotonic()
        ov.resize(760, 200)
        for s in STYLE_NAMES:
            ov.style_mode = s                 # 直接赋值，不走 setter（不写配置）
            ov._relayout()
            img = QImage(ov.width(), ov.height(), QImage.Format_ARGB32)
            img.fill(QColor(0, 0, 0, 0))
            p = QPainter(img)
            getattr(ov, "_paint_" + s)(p)
            p.end()
        res.append("render ok (%d styles)" % len(STYLE_NAMES))
        ov.hotkeys.unregister()
    except Exception:
        res.append("render FAIL: " + (traceback.format_exc().strip().splitlines()[-1]))
    _mark(res[-1])

    ok = not any("FAIL" in r for r in res)
    line = "[selftest] v%s %s :: %s" % (APP_VERSION, "PASS" if ok else "FAIL", " | ".join(res))
    log(line)
    _mark("RESULT " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    # 守护进程模式：不建 GUI，只负责监护 / 拉起主程序
    if SUPERVISE_FLAG in sys.argv:
        watch = 0
        if WATCH_PID_FLAG in sys.argv:
            try:
                watch = int(sys.argv[sys.argv.index(WATCH_PID_FLAG) + 1])
            except (IndexError, ValueError):
                watch = 0
        return run_supervisor(watch)

    # 打包后自检：Desktop-sing.exe --selftest（验证依赖收全，不拉守护进程、不改配置）
    if SELFTEST_FLAG in sys.argv:
        return _selftest()

    app = QApplication(sys.argv)
    app.setApplicationName("桌面歌词")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_app_icon())

    # 单实例守护：已有实例在运行时先请求它让位（升级自动接管），失败才放弃
    probe = QLocalSocket()
    probe.connectToServer(APP_NAME)
    if probe.waitForConnected(300):
        if _request_takeover():
            log("旧实例已让位，v%s 接管启动" % APP_VERSION)
        else:
            log("已有实例在运行且未响应接管请求，本次启动退出")
            try:
                styled_message(
                    None, "桌面歌词", "旧版本桌面歌词仍在运行且无法自动接管。",
                    "请右键托盘图标选择「退出」后再重新启动。", warning=True)
            except Exception:
                pass
            return
    probe.abort()
    guard = QLocalServer()
    QLocalServer.removeServer(APP_NAME)
    guard.listen(APP_NAME)

    _load_fonts()

    log("桌面歌词 v%s 启动（python %s）" % (APP_VERSION, platform.python_version()))
    watcher = MediaWatcher()
    watcher.start()

    overlay = LyricOverlay(watcher)
    overlay.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 打包成无控制台 exe 后，异常没地方看，额外落一份文件便于排查
        try:
            with open(os.path.join(CFG_DIR, "fatal.txt"), "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        log("fatal:\n" + traceback.format_exc())
        raise
