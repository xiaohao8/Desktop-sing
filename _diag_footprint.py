# -*- coding: utf-8 -*-
"""资源占用 / 体积 / 响应速度体检（离屏，不需要显示器）

量四件事，都是优化前后可直接对比的硬指标：

  1. 冷启动   —— import 模块 + 建窗 + 首帧渲染，各阶段耗时
  2. 常驻内存 —— 进程 WorkingSet（含峰值）
  3. 空闲 CPU —— 无歌 / 有歌暂停 / 播放 三种状态下的 CPU 占比
  4. 抓词延迟 —— 各来源单独耗时，以及"顺序择优"与"并行择优"的总耗时对比

用法：
    python _diag_footprint.py              # 全部
    python _diag_footprint.py --no-net     # 跳过联网项（只看启动/内存/CPU）
"""
import ctypes
import json
import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from ctypes import wintypes  # noqa: E402


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_k32 = None
_psapi = None


def cpu_time_seconds():
    """进程累计 CPU 时间（内核 + 用户），单位秒

    time.process_time() 在 Windows 上分辨率约 15.6ms —— 3 秒窗口里量化误差
    就有 0.5%，比它要测的东西还大（会出现"隐藏态比播放态更费"这种鬼结论）。
    GetProcessTimes 是 100ns 精度，果断换掉。
    """
    global _k32
    if _k32 is None:
        _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.GetProcessTimes.restype = wintypes.BOOL
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    c, e, k, u = (wintypes.FILETIME() for _ in range(4))
    if not _k32.GetProcessTimes(_k32.GetCurrentProcess(), ctypes.byref(c), ctypes.byref(e),
                                ctypes.byref(k), ctypes.byref(u)):
        return time.process_time()
    ticks = (k.dwHighDateTime << 32 | k.dwLowDateTime) + (u.dwHighDateTime << 32 | u.dwLowDateTime)
    return ticks / 1e7                       # FILETIME 单位 100ns


def rss_mb():
    """当前进程 WorkingSet / 峰值，单位 MB

    坑：GetCurrentProcess() 返回的是伪句柄 -1。不显式声明 restype = HANDLE 的话，
    ctypes 会按 32 位 c_int 传参，64 位下高 32 位被零扩展，句柄就废了 ——
    psapi 会一路返回 0（表现为"内存 0.0 MB"）。
    """
    global _k32, _psapi
    if _k32 is None:
        _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _k32.GetCurrentProcess.restype = wintypes.HANDLE
    if _psapi is None:
        _psapi = ctypes.WinDLL("psapi", use_last_error=True)
        for fn in (getattr(_psapi, "GetProcessMemoryInfo", None),
                   getattr(_k32, "K32GetProcessMemoryInfo", None)):
            if fn is not None:
                fn.restype = wintypes.BOOL
                fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    c = _PMC()
    c.cb = ctypes.sizeof(c)
    fn = getattr(_psapi, "GetProcessMemoryInfo", None) or getattr(_k32, "K32GetProcessMemoryInfo")
    if not fn(_k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        return 0.0, 0.0
    return c.WorkingSetSize / 1048576.0, c.PeakWorkingSetSize / 1048576.0


def cpu_percent(fn, seconds=3.0):
    """（已弃用，仅留作对照）忙等采样：轮询 processEvents 的占比，量具自身开销很重"""
    t0, c0 = time.time(), time.process_time()
    while time.time() - t0 < seconds:
        fn()
    return (time.process_time() - c0) / max(1e-6, time.time() - t0) * 100.0

print("=" * 68)
print("桌面歌词 · 资源占用体检")
print("=" * 68)

# ---------------------------------------------------------------- 冷启动
print("\n[1] 冷启动耗时（新进程，逐阶段）")
probe = r'''
import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
t0 = time.perf_counter()
import lyrics_overlay as L
t_imp = time.perf_counter() - t0
t1 = time.perf_counter()
from PySide6.QtWidgets import QApplication
app = QApplication([])
t_qt = time.perf_counter() - t1
t2 = time.perf_counter()
ov = L.LyricOverlay(L.MediaWatcher())
t_win = time.perf_counter() - t2
t3 = time.perf_counter()
ov.song = {"title": "起风了", "artist": "买辣椒也用券", "source": "qq", "cover": None}
ov.lines = [[i * 3.0, "测试歌词第%d行" % i] for i in range(40)]
ov.words = {i: [[i * 3.0 + j * 0.4, 0.4, "字"] for j in range(4)] for i in range(40)}
ov.status = "PLAYING"
for _ in range(30):
    ov._on_frame()
t_first = time.perf_counter() - t3
print("%.0f|%.0f|%.0f|%.0f|%.0f" % (t_imp * 1000, t_qt * 1000, t_win * 1000,
                                    t_first / 30 * 1000, (time.perf_counter() - t0) * 1000))
'''
r = subprocess.run([sys.executable, "-c", probe], cwd=BASE, capture_output=True, text=True)
line = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
if not line:
    print("  ! 探测失败:", (r.stderr or "")[-400:])
else:
    a, b, c, d, e = (float(x) for x in line.split("|"))
    print("  import 模块      %7.0f ms" % a)
    print("  QApplication     %7.0f ms" % b)
    print("  建悬浮窗         %7.0f ms" % c)
    print("  每帧渲染         %7.2f ms" % d)
    print("  ── 到首帧合计   %7.0f ms" % e)

# ---------------------------------------------------------------- 内存 / CPU
print("\n[2] 常驻内存 与 [3] 空闲 CPU（本进程）")
import lyrics_overlay as L                       # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer          # noqa: E402
from PySide6.QtWidgets import QApplication       # noqa: E402

app = QApplication([])

# 数真实 paintEvent 次数：光看 CPU% 会误判（窗口没被真正绘制时 CPU 自然≈0，
# 那是"没画"不是"优化了"）。必须把 CPU 和"实际画了几帧"配起来看。
# 注意：必须在建实例之前给**类**打桩 —— PySide6 的虚函数派发认的是类型属性。
_paints = [0]
_real_paint = L.LyricOverlay.paintEvent


def _counted_paint(self, event):
    _paints[0] += 1
    return _real_paint(self, event)


L.LyricOverlay.paintEvent = _counted_paint

ov = L.LyricOverlay(L.MediaWatcher())
ov.show()
app.processEvents()
r0 = rss_mb()
print("  启动后工作集      %6.1f MB（峰值 %.1f MB）" % r0)

SONG = {"title": "起风了", "artist": "买辣椒也用券", "source": "qq", "cover": None}
LINES = [[i * 3.0, "这一路上走走停停第%d句" % i] for i in range(60)]
WORDS = {i: [[i * 3.0 + j * 0.4, 0.4, chr(0x4E00 + j)] for j in range(6)] for i in range(60)}


def pump():
    app.processEvents()
    time.sleep(0.004)


# 统计真实驱动了多少帧 —— CPU 占比必须配上帧数才有意义
# （定时器停了 CPU 自然接近 0，光看百分比会误判成"优化成功"）
_frames = [0]
_real_frame = ov._on_frame


def _counted_frame(*a, **kw):
    _frames[0] += 1
    return _real_frame(*a, **kw)


ov._on_frame = _counted_frame


def cpu_percent_frames(seconds=3.0, keep_visible=True):
    """跑一段**真实的 Qt 事件循环**，量这段时间的进程 CPU 占比 + 实际帧率

    坑 1：早先这版是「while 循环里不停 processEvents()」—— 那个忙等本身就要吃掉
    2ms/轮，测出来的百分比主要是量具自己的开销，跟程序真实空转完全不是一回事
    （同一份代码 pause 态能测出 15%，而逐帧微基准只有 0.5ms）。
    坑 2：也不能用 app.exec() + app.quit() 限时 —— quit() 之后窗口在后续几轮里
    根本不再重绘，测出来的「0.0%」是假的。本地 QEventLoop 只退出这个循环、
    不动应用状态，窗口全程可见。
    keep_visible=False 用于测「隐藏态」：那种场景下绝不能再 show() 一次，
    否则量的是显示态，结论正好反了。
    """
    _frames[0] = 0
    _paints[0] = 0
    if keep_visible:
        ov.show()
    app.processEvents()
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    t0, c0 = time.time(), cpu_time_seconds()
    loop.exec()
    elapsed = max(1e-6, time.time() - t0)
    return ((cpu_time_seconds() - c0) / elapsed * 100.0,
            _frames[0] / elapsed, _paints[0] / elapsed)


# 无歌（等待态）
ov.song = None
ov.lines, ov.words = [], {}
ov._on_frame()
idle_cpu, idle_fps, idle_pps = cpu_percent_frames(3.0)

# 有歌但暂停
ov.song = dict(SONG)
ov.lines, ov.words = LINES, {}
ov.status = "PAUSED"
ov._on_frame()
pause_cpu, pause_fps, pause_pps = cpu_percent_frames(3.0)

# 播放 + 逐字动画（最重的状态）
ov.words = WORDS
ov.status = "PLAYING"
ov.anchor_pos, ov.anchor_ts = 6.0, time.monotonic()
play_cpu, play_fps, play_pps = cpu_percent_frames(3.0)

# 播放中但窗口被隐藏（托盘「隐藏歌词」）：这条最容易漏，隐藏了还在逐帧画就白烧
ov.hide()
app.processEvents()
hidden_cpu, hidden_fps, hidden_pps = cpu_percent_frames(2.0, keep_visible=False)
ov.show()
app.processEvents()

r1 = rss_mb()
print("  跑完三态工作集    %6.1f MB（峰值 %.1f MB）" % r1)
for tag, c, f, p in (("空闲（无歌）", idle_cpu, idle_fps, idle_pps),
                     ("空闲（暂停）", pause_cpu, pause_fps, pause_pps),
                     ("播放（逐字）", play_cpu, play_fps, play_pps),
                     ("播放（已隐藏）", hidden_cpu, hidden_fps, hidden_pps)):
    print("  CPU %-12s %6.1f %%   %5.1f 帧/秒   重绘 %5.1f 次/秒" % (tag, c, f, p))

# ---------------------------------------------------------------- 抓词延迟
if "--no-net" not in sys.argv:
    print("\n[4] 抓词延迟（真实联网，单曲）")
    title, artist = "起风了", "买辣椒也用券"
    q = ("%s %s" % (title, artist)).strip()

    def timed(name, fn):
        t = time.perf_counter()
        try:
            v = fn()
            ok = bool(v) and not (isinstance(v, tuple) and not v[0])
        except Exception as exc:
            v, ok = repr(exc)[:60], False
        dt = time.perf_counter() - t
        print("     %-10s %6.0f ms  %s" % (name, dt * 1000, "ok" if ok else "空/失败"))
        return dt, ok

    seq = 0.0
    for nm, f in (("QQ搜索", lambda: L.fetch_qq_search(q)),
                  ("网易云搜索", lambda: L.fetch_netease_search(q)),
                  ("酷狗搜索", lambda: L.fetch_kugou_search(q)),
                  ("LRCLIB", lambda: L.fetch_lrclib_candidates(title, artist))):
        d, _ = timed(nm, f)
        seq += d
    print("     顺序合计约 %.0f ms（实际择优会在拿到满配时提前结束）" % (seq * 1000))

    print("\n  端到端 fetch_lyrics（命中缓存 = 0 网络）")
    for tag in ("首次", "缓存"):
        if tag == "缓存":
            key = ("%s|%s" % (title, artist)).lower().strip()
            cp = L._cache_path(key)
            if not os.path.exists(cp):
                print("     (无缓存文件，跳过)")
                break
        t = time.perf_counter()
        lines, words, cover, trans = L.fetch_lyrics(title, artist, duration=325.0)
        print("     %-6s %6.0f ms  行=%d 逐字=%d 翻译=%d"
              % (tag, (time.perf_counter() - t) * 1000, len(lines), len(words), len(trans)))

print("\n" + "=" * 68)
