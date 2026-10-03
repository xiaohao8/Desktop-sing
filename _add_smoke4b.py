# -*- coding: utf-8 -*-
"""给第四轮 async_fetch_ordering 补一条断言：SMTC 已带封面时不得重复下载。

播放器（SMTC）本身会带 cover 数据，_apply_media 已把 cover_pix 填好；
这时再 http_get 一遍就是白下几百 KB，补发通道还会把图丢弃。
幂等 + CRLF 安全。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.py")
MARK = "# --- SMTC 已带封面时不得重复下载"

OLD = '''        # --- 已有封面时不得覆盖
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
'''

NEW = '''        # --- 已有封面时不得覆盖
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

        # --- SMTC 已带封面时不得重复下载
        #     _apply_media 收到 cover 字节就会填好 cover_pix；此时 worker
        #     再去 http_get 就是白下一张几百 KB 的图，补发通道还会丢弃它。
        calls[:] = []
        ov4 = _mk_overlay()
        png_q = QPixmap()
        png_q.loadFromData(PNG)
        from PySide6.QtCore import QBuffer
        buf = QBuffer()
        buf.open(QBuffer.ReadWrite)
        png_q.save(buf, "PNG")
        L.http_get = fake_http
        L.fetch_lyrics = fake_fetch
        ov4._apply_media({"title": "晴天", "artist": "周杰伦",
                          "cover": bytes(buf.data())})
        d3 = _t.perf_counter() + 3
        while _t.perf_counter() < d3 and not calls:
            QApplication.processEvents()
            _t.sleep(0.005)
        ck(not calls,
           "SMTC 已带封面却仍下载了封面（%d 次，白流 bandwidth）" % len(calls))
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if MARK in src:
        print("skip：断言已存在")
        return 0
    nl = "\r\n" if "\r\n" in src else "\n"
    old, new = OLD.replace("\n", nl), NEW.replace("\n", nl)
    if src.count(old) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(old))
        return 1
    src = src.replace(old, new, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("ok：补上「已有封面不重复下载」断言")
    return 0


if __name__ == "__main__":
    sys.exit(main())
