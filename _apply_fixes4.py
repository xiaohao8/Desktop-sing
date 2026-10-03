# -*- coding: utf-8 -*-
"""v2.0.1 第四轮修复：异步封面 + 停止播放作废在途请求。

两处改动（主文件是 CRLF，必须用 io.open(newline='') 精确替换）：
  1. _apply_media(None) 递增 _req_id，让在途的旧请求作废；
     并修掉托盘气泡在 song 为 None 时文案退化成「当前歌手/空标题」的问题。
  2. 封面下载从歌词主路径摘出去：worker 先 emit 歌词，封面下完再补发
     cover_ready 信号。实测歌词到手 6ms 却要为封面多等 362ms（网络差时
     最多压 5 秒 timeout），而封面只是装饰。
幂等：已改过则跳过。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")

# ---------------------------------------------------------------- 改动 1+2
OLD_TAIL = '''    def _apply_media(self, info):
        if info is None:
            self.song = None
            self.cover_pix = None'''
NEW_TAIL = '''    def _apply_media(self, info):
        if info is None:
            # 停止播放 / 播放器退出也必须让**在途的歌词请求作废**。
            # _req_id 原先只在 _start_fetch 里自增，而这条路径不走
            # _start_fetch —— 上一首的 worker 回来时 req_id 仍然匹配，
            # 于是「已停止」的界面上又冒出上一首的歌词，还会弹一个
            # 错配气泡（此时 self.song 是 None，气泡文案还会退化成
            # 「没找到 当前歌手 的《空标题》版本」）。这里显式作废。
            self._req_id += 1
            self.song = None
            self.cover_pix = None'''

# ---------------------------------------------------------------- 改动 3
OLD_SIGNAL = '''    fetched = Signal(object)  # payload=(req_id, lines, words, fallback_cover_bytes)'''
NEW_SIGNAL = '''    fetched = Signal(object)  # payload=(req_id, lines, words, fallback_cover_bytes, trans, singer_ok)
    cover_ready = Signal(object)  # payload=(req_id, cover_bytes)：封面是补充，不阻塞歌词上屏'''

# ---------------------------------------------------------------- 改动 4
OLD_WORKER = '''            fallback_cover = None
            if self._req_id == req_id and self.cover_pix is None and cover_url:
                try:
                    fallback_cover = http_get(cover_url, timeout=5)
                except Exception:
                    fallback_cover = None
            self.fetched.emit((req_id, lines or [], words or {},
                               fallback_cover, trans or [], bool(singer_ok)))
'''
NEW_WORKER = '''            # 先把歌词发出去，**不要等封面**：封面是装饰，歌词才是主路径。
            # 原先在这里同步 http_get(cover, timeout=5) 再 emit，实测「晴天」
            # 歌词 6ms 就到手，却因为封面多等 362ms 才上屏；网络差时最多压 5 秒。
            self.fetched.emit((req_id, lines or [], words or {},
                               None, trans or [], bool(singer_ok)))
            # 封面改走独立补发通道：下完再单独 emit，UI 那时已经显示歌词了。
            if cover_url:
                try:
                    self.cover_ready.emit((req_id, http_get(cover_url, timeout=5)))
                except Exception:
                    log("cover download failed: " + traceback.format_exc())
'''

# ---------------------------------------------------------------- 改动 5
OLD_CONNECT = '''        self.fetched.connect(self._on_fetched)'''
NEW_CONNECT = '''        self.fetched.connect(self._on_fetched)
        self.cover_ready.connect(self._on_cover_ready)'''

# ---------------------------------------------------------------- 改动 6
OLD_ONFETCHED_TAIL = '''        self._trans_map = self._build_trans_map()
        self._reset_line_state()
        self._spans_cache.clear()
        if self.cover_pix is None and fallback_cover:
            pix = QPixmap()
            if pix.loadFromData(fallback_cover):
                self.cover_pix = pix
                self._cover_scaled = None
                self._vinyl_pix = None
                self._resolve_accent()
        self._relayout()
'''
NEW_ONFETCHED_TAIL = '''        self._trans_map = self._build_trans_map()
        self._reset_line_state()
        self._spans_cache.clear()
        if self.cover_pix is None and fallback_cover:
            self._apply_cover_bytes(fallback_cover)
        self._relayout()

    def _apply_cover_bytes(self, data: bytes) -> bool:
        """封面字节 -> cover_pix，联动失效缩放缓存并重算主色。"""
        pix = QPixmap()
        if not data or not pix.loadFromData(data):
            return False
        self.cover_pix = pix
        self._cover_scaled = None
        self._vinyl_pix = None
        self._resolve_accent()
        return True

    def _on_cover_ready(self, payload):
        """封面补发通道：晚于歌词到达，只在仍是当前请求且确实没封面时才用。

        期间用户可能已经切歌/停止（req_id 变了）或播放器已送来封面
        （cover_pix 已有值），这两种情况都必须丢弃，否则会把上一首的
        封面糊到当前歌上。
        """
        req_id, data = payload[:2]
        if req_id != self._req_id or self.song is None or self.cover_pix is not None:
            return
        if self._apply_cover_bytes(data):
            self._relayout()
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    orig = src
    # 主文件是 CRLF：用 newline='' 读进来 \r\n 会被原样保留，锚点里的 \n
    # 匹配不上（Edit 工具同款坑）。按实际换行风格统一转换锚点。
    nl = "\r\n" if "\r\n" in src else "\n"
    edits = [
        ("作废在途请求（_apply_media(None) 递增 _req_id）", OLD_TAIL, NEW_TAIL),
        ("新增 cover_ready 信号", OLD_SIGNAL, NEW_SIGNAL),
        ("worker 先发歌词、封面改走补发通道", OLD_WORKER, NEW_WORKER),
        ("连接 cover_ready 信号", OLD_CONNECT, NEW_CONNECT),
        ("_on_fetched 拆出 _apply_cover_bytes / _on_cover_ready",
         OLD_ONFETCHED_TAIL, NEW_ONFETCHED_TAIL),
    ]
    for name, old, new in edits:
        old, new = old.replace("\n", nl), new.replace("\n", nl)
        if new in src:
            print("skip  %s（已应用）" % name)
            continue
        n = src.count(old)
        if n != 1:
            print("FAIL  %s：锚点出现 %d 次" % (name, n))
            return 1
        src = src.replace(old, new, 1)
        print("ok    %s" % name)
    if src == orig:
        print("nothing to do")
        return 0
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("written: %s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
