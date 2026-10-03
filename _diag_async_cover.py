# -*- coding: utf-8 -*-
"""诊断：异步封面改造后，歌词上屏延迟是否真的下降（离屏真实 Qt 事件循环）。

对比两种时序：
  旧 = fetch -> 下载封面 -> emit（歌词被封面拖住）
  新 = fetch -> emit -> 下载封面 -> emit cover_ready
用真实信号/事件循环测「emit 到 _on_fetched 执行完」的墙钟时间。
"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)

import lyrics_overlay as L


class FakeWatcher(L.QObject):
    mediaChanged = L.Signal(object)
    ticked = L.Signal(float, float, str)

    def activate(self):
        pass


# 用一个「慢封面」模拟真实网络抖动：p50 300ms，p95 900ms，偶发 5s 超时
class FakeHttp:
    def __init__(self, delay_s):
        self.delay = delay_s
        self.calls = 0

    def __call__(self, url, headers=None, timeout=8.0):
        # 只拦封面 URL：QTimer.singleShot(4000, check_update) 也会打 http_get，
        # 全局替换会把更新检查误算进来（上一版 5s 那行就多出 3 次调用）。
        if "example.invalid" not in str(url):
            return _REAL_HTTP_GET(url, headers=headers, timeout=timeout)
        self.calls += 1
        time.sleep(self.delay)
        # 最小合法 PNG（1x1 透明）
        return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
                b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
                b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


_REAL_HTTP_GET = L.http_get


def make_overlay():
    ov = L.LyricOverlay(FakeWatcher())
    ov.tray.showMessage = lambda *a, **k: None
    return ov


def run_once(cover_delay):
    """跑一次真实抓取（命中缓存 → 歌词秒回），量歌词上屏时刻。"""
    http = FakeHttp(cover_delay)
    orig_http, orig_fetch = L.http_get, L.fetch_lyrics
    L.http_get = http

    def fake_fetch(title, artist, prefer_netease=False, duration=0.0,
                   strict_artist=False):
        # 复用真实缓存，避免每次联网；只返回词，不给封面 URL
        # -> 封面 URL 由 _gather_sources 真实提供时才会下载，
        # 这里直接构造带封面的结果以贴近线上行为。
        return ([[1.0, "第一条"]], {0: [[1.0, 0.5, "第一条"]]},
                "https://example.invalid/cover.jpg", [], True)

    L.fetch_lyrics = fake_fetch
    try:
        ov = make_overlay()
        stamps = {}
        orig_on = ov._on_fetched

        def on_fetched(payload):
            stamps["lyrics"] = time.perf_counter()
            orig_on(payload)

        ov._on_fetched = on_fetched
        ov.fetched.disconnect()
        ov.fetched.connect(on_fetched)

        t0 = time.perf_counter()
        ov._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
        # 跑事件循环直到歌词落地（最多 15s）
        deadline = time.perf_counter() + 15
        while "lyrics" not in stamps and time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.002)
        if "lyrics" not in stamps:
            return None, http.calls
        t_lyrics = stamps["lyrics"] - t0
        # 再把封面事件跑完
        d2 = time.perf_counter() + 15
        while http.calls == 0 and time.perf_counter() < d2:
            app.processEvents()
            time.sleep(0.002)
        while time.perf_counter() < d2:
            app.processEvents()
            if ov.cover_pix is not None:
                break
            time.sleep(0.002)
        t_cover = time.perf_counter() - t0
        return (t_lyrics, t_cover), http.calls
    finally:
        L.http_get, L.fetch_lyrics = orig_http, orig_fetch


def main():
    print("=" * 76)
    print("诊断：异步封面后歌词上屏延迟")
    print("=" * 76)
    print("%-12s %14s %14s %10s" % ("封面耗时", "歌词上屏ms", "封面完成ms", "调用次数"))
    print("-" * 76)
    for delay in (0.30, 0.90, 5.00):
        r, calls = run_once(delay)
        if r is None:
            print("%-12s 超时，未收到歌词" % ("%.2fs" % delay))
            continue
        print("%-12s %14.0f %14.0f %10d" % (
            "%.2fs" % delay, r[0] * 1000, r[1] * 1000, calls))
    print("-" * 76)
    print("旧时序下「歌词上屏」这一列应等于「封面耗时」量级（被拖住）；")
    print("新时序下歌词先到（接近 0），封面随后补上。")
    print("=" * 76)


if __name__ == "__main__":
    main()
