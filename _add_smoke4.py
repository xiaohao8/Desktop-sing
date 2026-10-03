# -*- coding: utf-8 -*-
"""给冒烟测试加第四轮回归组：stale_fetch_guard + async_cover。

覆盖两个修复：
  1. _apply_media(None) 必须递增 _req_id 作废在途请求（否则停止后旧歌词
     回填 + 弹托盘气泡，且气泡文案退化成「当前歌手/空标题」）
  2. 封面下载不得阻塞歌词上屏（worker 先 emit 歌词，封面走 cover_ready）
CRLF 安全 + 幂等。锚点插在 check("cache prune report", ...) 之后。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.py")
MARK = 'check("async fetch ordering", async_fetch_ordering)'

ANCHOR = 'check("cache prune report", cache_prune_report)'

BLOCK = '''

# ======================================================================
# 第四轮：停止作废在途请求 + 封面不阻塞歌词
# ======================================================================
from PySide6.QtCore import QObject as _QObject          # noqa: E402

''' + '''class _FakeWatcher(_QObject):
    """LyricOverlay 构造需要一个带 mediaChanged/ticked/activate 的 watcher。

    ⚠️ Qt 信号必须声明为**类属性**：写在 __init__ 里拿到的是未绑定的
    Signal 对象，没有 connect 方法（诊断脚本在这上面栽过一次）。
    """
    mediaChanged = L.Signal(object)
    ticked = L.Signal(float, float, str)

    def activate(self):
        pass


def _mk_overlay():
    ov = L.LyricOverlay(_FakeWatcher())
    ov.tray.showMessage = lambda *a, **k: None
    return ov


def stale_fetch_guard():
    """停止播放 / 切走后，在途的旧歌词请求必须被丢弃"""
    fails = []

    def ck(cond, why):
        if not cond:
            fails.append(why)

    # --- 1) 停止后旧歌词不得回填
    ov = _mk_overlay()
    ov._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
    mid = ov._req_id
    ov._apply_media(None)                    # 停止播放
    ck(ov._req_id != mid, "停止播放没有作废在途请求（_req_id 未变）")
    ov._on_fetched((mid, [[1.0, "故事的小黄花"]], {}, None, [], True))
    ck(len(ov.lines) == 0, "停止后旧歌词被回填: %r" % (ov.lines,))
    ck(ov.song is None, "停止后 song 应仍为 None")

    # --- 2) 停止后错配结果不得弹气泡
    ov2 = _mk_overlay()
    got = []
    ov2.tray.showMessage = lambda *a, **k: got.append(a)
    ov2._apply_media({"title": "无所谓", "artist": "杨千嬅", "cover": None})
    mid2 = ov2._req_id
    ov2._apply_media(None)
    ov2._on_fetched((mid2, [[1.0, "随便啦"]], {}, None, [], False))   # 错配
    ck(not got, "停止后仍弹托盘气泡打扰用户: %r" % (got[:1],))

    # --- 3) 停止后播新歌，旧歌词不得覆盖新歌
    ov3 = _mk_overlay()
    ov3._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
    mid3 = ov3._req_id
    ov3._apply_media(None)
    ov3._apply_media({"title": "海阔天空", "artist": "Beyond", "cover": None})
    ov3._on_fetched((ov3._req_id, [[1.0, "今天我 寒夜里看雪飘过"]], {}, None, [], True))
    ov3._on_fetched((mid3, [[9.9, "旧歌残留"]], {}, None, [], True))
    texts = [t for _tt, t in ov3.lines]
    ck("旧歌残留" not in texts, "旧歌词覆盖了新歌: %r" % (texts,))

    # --- 4) 气泡文案在 song 为 None 时不得退化（回归二次 bug）
    #      修好作废逻辑后这条自然不该触发；这里直接验证渲染文案的前置条件：
    #      有 song 时文案含真实歌手/歌名，不含占位符。
    ov4 = _mk_overlay()
    got4 = []
    ov4.tray.showMessage = lambda *a, **k: got4.append(a)
    ov4._apply_media({"title": "无所谓", "artist": "杨千嬅", "cover": None})
    rid = ov4._req_id
    ov4._on_fetched((rid, [[1.0, "随便啦"]], {}, None, [], False))
    ck(len(got4) == 1, "在途错配应弹一次气泡: %r" % (got4[:1],))
    if got4:
        msg = got4[0][1]
        ck("杨千嬅" in msg, "气泡缺歌手名: %r" % msg)
        ck("无所谓" in msg, "气泡缺歌名: %r" % msg)
        ck("当前歌手" not in msg and "《》" not in msg,
           "气泡文案退化成占位符: %r" % msg)

    for w in fails:
        check("stale fetch guard", lambda w=w: (_ for _ in ()).throw(AssertionError(w)))
    return True


check("stale fetch guard", stale_fetch_guard)


def async_fetch_ordering():
    """歌词上屏不得被封面下载阻塞；封面走 cover_ready 补发，且只发一次"""
    import time as _t
    PNG = (b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR"
           b"\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x01\\x08\\x06\\x00\\x00\\x00"
           b"\\x1f\\x15\\xc4\\x89\\x00\\x00\\x00\\nIDATx\\x9cc\\x00\\x01"
           b"\\x00\\x00\\x05\\x00\\x01\\r\\n-\\xb4\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82")
    fails = []

    def ck(cond, why):
        if not cond:
            fails.append(why)

    real_http, real_fetch = L.http_get, L.fetch_lyrics
    calls = []

    def fake_http(url, headers=None, timeout=8.0):
        # 只拦封面；update_check 的定时器也会打 http_get，不能算进来
        if "example.invalid" not in str(url):
            return real_http(url, headers=headers, timeout=timeout)
        calls.append(str(url))
        _t.sleep(0.6)                        # 模拟慢封面
        return PNG

    def fake_fetch(title, artist, prefer_netease=False, duration=0.0,
                   strict_artist=False):
        return ([[1.0, "第一条"]], {0: [[1.0, 0.5, "第一条"]]},
                "https://example.invalid/cover.jpg", [], True)

    def run():
        calls[:] = []
        L.http_get = fake_http
        L.fetch_lyrics = fake_fetch
        ov = _mk_overlay()
        stamps = {}
        orig = ov._on_fetched

        def wrapped(payload):
            stamps["t"] = _t.perf_counter()
            orig(payload)

        ov.fetched.disconnect()
        ov.fetched.connect(wrapped)
        t0 = _t.perf_counter()
        ov._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
        deadline = _t.perf_counter() + 10
        while "t" not in stamps and _t.perf_counter() < deadline:
            QApplication.processEvents()
            _t.sleep(0.002)
        ck("t" in stamps, "歌词信号始终没来")
        t_lyrics = (stamps["t"] - t0) if "t" in stamps else 99
        # 跑完封面
        d2 = _t.perf_counter() + 10
        while _t.perf_counter() < d2 and (not calls or ov.cover_pix is None):
            QApplication.processEvents()
            _t.sleep(0.002)
        t_cover = _t.perf_counter() - t0
        return t_lyrics, t_cover, ov

    try:
        t_lyrics, t_cover, ov = run()
        ck(len(calls) == 1, "封面应只请求一次，实际 %d 次" % len(calls))
        ck(t_lyrics < 0.25,
           "歌词上屏被封面拖住了：%.0f ms（封面 600ms）" % (t_lyrics * 1000))
        ck(ov.cover_pix is not None and not ov.cover_pix.isNull(),
           "封面补发通道没把封面装上")
        ck(len(ov.lines) == 1, "封面补发不该动歌词: %r" % (ov.lines,))

        # --- 过期封面必须丢弃：期间用户已切歌
        t0 = _t.perf_counter()
        ov2 = _mk_overlay()
        L.http_get = fake_http
        L.fetch_lyrics = fake_fetch
        ov2._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
        stale_id = ov2._req_id
        ov2._apply_media(None)               # 立刻停止
        ov2._on_cover_ready((stale_id, PNG))  # 旧封面这时才到
        ck(ov2.cover_pix is None, "停止后过期封面仍被采纳")

        # --- 已有封面时不得覆盖
        ov3 = _mk_overlay()
        ov3.cover_pix = QPixmap(8, 8)
        before = ov3.cover_pix.width()
        ov3._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
        rid = ov3._req_id
        ov3.cover_pix = QPixmap(8, 8)
        before = ov3.cover_pix.width()
        ov3._on_cover_ready((rid, PNG))
        ck(ov3.cover_pix.width() == before,
           "已有封面被补发通道覆盖了")

    finally:
        L.http_get, L.fetch_lyrics = real_http, real_fetch

    for w in fails:
        check("async fetch ordering", lambda w=w: (_ for _ in ()).throw(AssertionError(w)))
    return True


check("async fetch ordering", async_fetch_ordering)
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if MARK in src:
        print("skip：第四轮回归组已存在")
        return 0
    nl = "\r\n" if "\r\n" in src else "\n"
    anchor, block = ANCHOR.replace("\n", nl), BLOCK.replace("\n", nl)
    if src.count(anchor) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(anchor))
        return 1
    src = src.replace(anchor, anchor + block, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("written: %s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
