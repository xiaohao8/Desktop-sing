# -*- coding: utf-8 -*-
"""补一处退化：SMTC 已经给了封面时，不要再重复下载一次封面。

异步化时把原来的守卫 `self._req_id == req_id and self.cover_pix is None`
一起丢了。后果：播放器（SMTC）本身会带 cover 数据 → _apply_media 已经把
cover_pix 填好 → worker 仍然 http_get(cover_url, timeout=5) 白下一张
几百 KB 的图，下完 _on_cover_ready 又因为 cover_pix is not None 丢弃。
纯浪费带宽和一次外网请求。

修法：在 worker 里补回守卫（req_id 已失效就别下；已有封面就别下）。
CRLF 安全 + 幂等。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")

OLD = '''            # 封面改走独立补发通道：下完再单独 emit，UI 那时已经显示歌词了。
            if cover_url:
                try:
                    self.cover_ready.emit((req_id, http_get(cover_url, timeout=5)))
                except Exception:
                    log("cover download failed: " + traceback.format_exc())
'''

NEW = '''            # 封面改走独立补发通道：下完再单独 emit，UI 那时已经显示歌词了。
            # ⚠️ 守卫不能丢：SMTC 本身常带 cover 数据，_apply_media 已把
            # cover_pix 填好；无条件下载就是白下一张几百 KB 的图，下完
            # _on_cover_ready 又会因 cover_pix is not None 丢弃 —— 纯浪费。
            # req_id 也一并校验：切歌后旧封面没必要再下。
            if cover_url and self._req_id == req_id and self.cover_pix is None:
                try:
                    self.cover_ready.emit((req_id, http_get(cover_url, timeout=5)))
                except Exception:
                    log("cover download failed: " + traceback.format_exc())
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    old, new = OLD.replace("\n", nl), NEW.replace("\n", nl)
    if new in src:
        print("skip：守卫已在")
        return 0
    if src.count(old) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(old))
        return 1
    src = src.replace(old, new, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("ok：补回封面下载守卫")
    return 0


if __name__ == "__main__":
    sys.exit(main())
