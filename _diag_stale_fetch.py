# -*- coding: utf-8 -*-
"""诊断：停止播放（_apply_media(None)）后，在途的旧请求会不会把歌词回填回来。

_req_id 只在 _start_fetch 里自增。_apply_media(None) 是「播放器停了/切走了」，
它不走 _start_fetch，所以 _req_id 不变 → 上一首的 worker 回来时
`req_id != self._req_id` 判不出来 → _on_fetched 照样把旧歌词写进界面。
"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

import lyrics_overlay as L


class FakeWatcher(L.QObject):
    """信号必须是**类属性**（Qt 的绑定机制），在 __init__ 里赋值拿不到 connect。"""

    mediaChanged = L.Signal(object)
    ticked = L.Signal(float, float, str)

    def activate(self):
        pass


def build_overlay():
    ov = L.LyricOverlay(FakeWatcher())
    balloons = []
    ov.tray.showMessage = lambda *a, **k: balloons.append(a)
    return ov, balloons


def scenario_stop_during_fetch():
    """场景：歌词正在抓取，用户按了停止。"""
    ov, balloons = build_overlay()
    ov._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
    mid = ov._req_id
    # 模拟 worker 抓完回来（此刻用户已停止播放）
    ov._apply_media(None)               # 停止：song=None, lines=[]
    print("  停止后 song=%r lines=%d" % (ov.song, len(ov.lines)))
    ov._on_fetched((mid, [[1.0, "故事的小黄花"]], {}, None, [], True))
    print("  旧请求回填后 song=%r lines=%d" % (ov.song, len(ov.lines)))
    leaked = len(ov.lines) > 0
    print("  → %s" % ("❌ 旧歌词被回填到已停止的界面" if leaked else "✓ 正确丢弃"))
    return leaked


def scenario_stop_then_new_song():
    """场景：停止后立刻播新歌，旧请求回填 —— 新歌被旧歌词覆盖。"""
    ov, balloons = build_overlay()
    ov._apply_media({"title": "晴天", "artist": "周杰伦", "cover": None})
    mid = ov._req_id
    ov._apply_media(None)
    ov._apply_media({"title": "海阔天空", "artist": "Beyond", "cover": None})
    new_lines = [[1.0, "今天我 寒夜里看雪飘过"]]
    new_id = ov._req_id
    ov._on_fetched((new_id, new_lines, {}, None, [], True))   # 新歌先回
    ov._on_fetched((mid, [[9.9, "旧歌残留"]], {}, None, [], True))  # 旧歌后回
    texts = [t for _tt, t in ov.lines]
    ok = "旧歌残留" not in texts
    print("  新歌回填后 lines=%r" % (texts,))
    print("  → %s" % ("✓ 旧歌词被正确丢弃" if ok else "❌ 旧歌词覆盖了新歌"))
    return not ok


def scenario_mismatch_balloon_after_stop():
    """场景：停止后旧请求回填，还弹了个「疑似错配」托盘气泡。"""
    ov, balloons = build_overlay()
    ov._apply_media({"title": "无所谓", "artist": "杨千嬅", "cover": None})
    mid = ov._req_id
    ov._apply_media(None)
    ov._on_fetched((mid, [[1.0, "随便啦"]], {}, None, [], False))  # singer_ok=False
    print("  停止后收到错配结果，气泡数=%d 内容=%r" % (len(balloons), balloons[:1]))
    bad = len(balloons) > 0
    print("  → %s" % ("❌ 停止后仍弹出托盘气泡打扰用户" if bad else "✓ 未打扰"))
    return bad


def main():
    print("=" * 74)
    print("诊断：_apply_media(None) 不递增 _req_id，旧请求回填")
    print("=" * 74)
    print("[1] 停止播放后旧歌词回填")
    r1 = scenario_stop_during_fetch()
    print()
    print("[2] 停止后播新歌，旧歌词覆盖新歌")
    r2 = scenario_stop_then_new_song()
    print()
    print("[3] 停止后仍弹托盘气泡")
    r3 = scenario_mismatch_balloon_after_stop()
    print()
    print("=" * 74)
    print("结论：%d/3 个场景复现问题" % sum([r1, r2, r3]))
    print("=" * 74)
    return 0 if sum([r1, r2, r3]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
