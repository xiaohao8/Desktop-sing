# -*- coding: utf-8 -*-
"""抓词延迟 A/B 对比：旧「顺序轮询」vs 新「并行竞速」

每首歌跑两轮：

  A. **全量探针**：「打桩」后把四个源全部并发拉起并**等齐**，记录每个源各自的耗时与候选。
     新实现会在拿到满配时提前收工，被丢弃的源就没观测值，所以必须单独补一轮，
     否则旧实现的耗时会被低估（比较不公平）。
  B. **实测新实现**：清掉本地缓存，真跑一次 ``_gather_sources``，量真实墙钟耗时。

然后拿 A 轮的「单源耗时 + 候选」离线重放旧算法，算出旧实现的耗时：旧代码是
QQ -> 网易云 -> 酷狗 顺序试，拿不到逐字再单独等 LRCLIB，缺逐字时还会
**再请求一次网易云**，这些都如实累加。

用法：
    python _diag_fetch_latency.py
    python _diag_fetch_latency.py --tracks 起风了/买辣椒也用券,Hello/Adele
"""
from __future__ import annotations

import os
import sys
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

import lyrics_overlay as L  # noqa: E402

TRACKS = [
    ("起风了", "买辣椒也用券"),        # 国内源满配
    ("晴天", "周杰伦"),                # 国内源
    ("Hello", "Adele"),               # 海外
    ("Blinding Lights", "The Weeknd"),
]

ALL_SRC = ("qq", "netease", "kugou", "lrclib")

# ----------------------------------------------------------------- 打桩
_REAL_FETCH_SOURCE = L._fetch_source
_lock = threading.Lock()
_obs = {}          # src -> {"ms": 耗时, "cand": 候选}


def _stub(src, query, title_c, artist_c):
    t0 = time.perf_counter()
    try:
        cand = _REAL_FETCH_SOURCE(src, query, title_c, artist_c)
    except Exception as exc:                       # 记下来但不要中断整首歌
        cand = None
        print("        [warn] %s 抛错: %r" % (src, exc))
    with _lock:
        _obs[src] = {"ms": (time.perf_counter() - t0) * 1000.0, "cand": cand}
    return cand


L._fetch_source = _stub


def _probe_all(query, title, artist):
    """A 轮：四个源全并发拉起并等齐，保证观测完整（不受提前收工影响）"""
    global _obs
    _obs = {}
    ths = [threading.Thread(target=_stub, args=(s, query, title, artist), daemon=True)
           for s in ALL_SRC]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=max(L._FETCH_TIMEOUT.values()) + 3.0)


def _simulate_old(order):
    """按旧实现的顺序重放一遍，返回估算耗时 ms

    - 逐个源串行：耗时累加，拿到「逐字 + 翻译」立即 break；
    - 仍缺正文或缺逐字：额外串行等一次 LRCLIB（旧版 timeout=6s，本身就会等到 6s 上限）；
    - 正文在手但缺逐字/翻译且胜出源不是网易云：**再发一次网易云请求**（旧代码确有这一步）。
    """
    total, lines, words, trans, best, used = 0.0, [], {}, [], -1, None
    for src in order:
        o = _obs.get(src)
        if not o:
            continue
        total += o["ms"]
        cand = o["cand"]
        if not cand or not cand.get("lines"):
            continue
        sc = L.score_lyrics(cand["lines"], cand["words"], cand["trans"], 325.0)
        if sc > best:
            best, used = sc, src
            lines, words, trans = cand["lines"], cand["words"], cand["trans"]
        if words and trans:
            break
    if not lines or not words:
        o = _obs.get("lrclib")
        if o:
            total += max(o["ms"], 100.0)
    if lines and (not words or not trans) and used != "netease":
        o = _obs.get("netease")
        if o:
            total += o["ms"]                     # 旧版这里会重新搜一次网易云
    return total


def main():
    if "--tracks" in sys.argv:
        raw = sys.argv[sys.argv.index("--tracks") + 1]
        tracks = []
        for item in raw.split(","):
            if "/" in item:
                t, a = item.split("/", 1)
                tracks.append((t.strip(), a.strip()))
    else:
        tracks = TRACKS

    print("=" * 70)
    print("抓词延迟 A/B：旧「顺序轮询」vs 新「并行竞速」")
    print("=" * 70)

    rows = []
    for title, artist in tracks:
        key = ("%s|%s" % (title, artist)).lower().strip()
        cp = L._cache_path(key)
        query = ("%s %s" % (title, artist)).strip()

        # A 轮：全量探针（等齐四源，保证旧实现估算有完整数据）
        t0 = time.perf_counter()
        _probe_all(query, title, artist)
        probe_wall = (time.perf_counter() - t0) * 1000.0

        # B 轮：实测新实现（清缓存，走真实网络）
        if os.path.exists(cp):
            try:
                os.remove(cp)
            except OSError:
                pass
        t0 = time.perf_counter()
        lines, words, trans, cover, used, by_src = L._gather_sources(
            query, title, artist, 325.0, False)
        new_ms = (time.perf_counter() - t0) * 1000.0

        order = ("qq", "netease", "kugou")
        old_ms = _simulate_old(order)

        print("\n%s - %s" % (title, artist))
        print("  胜出来源     %s   行=%d 逐字=%d 翻译=%d"
              % (used or "无", len(lines), len(words), len(trans)))
        for src in ALL_SRC:
            o = _obs.get(src)
            if not o:
                print("    %-8s       -   未观测" % src)
                continue
            c = o["cand"]
            got = "无结果" if not c else ("%d行/%d逐字/%d翻译"
                                          % (len(c["lines"]), len(c["words"]), len(c["trans"])))
            flag = "  <- 慢源" if o["ms"] > 1000 else ""
            print("    %-8s %7.0f ms   %s%s" % (src, o["ms"], got, flag))
        print("  旧顺序实现  %7.0f ms （估算，含二次请求网易云）" % old_ms)
        print("  新并行实现  %7.0f ms   =>  快 %.1fx" % (new_ms, old_ms / new_ms if new_ms else 0))
        print("  （全量探针等齐四源的墙钟 %.0f ms，仅用于观测，不代表新实现耗时）" % probe_wall)
        rows.append((title, old_ms, new_ms))

    if rows:
        print("\n" + "-" * 70)
        avg_old = sum(r[1] for r in rows) / len(rows)
        avg_new = sum(r[2] for r in rows) / len(rows)
        print("平均：旧 %.0f ms  ->  新 %.0f ms   整体提速 %.1fx"
              % (avg_old, avg_new, (avg_old / avg_new) if avg_new else 0))
        print("最坏：旧 %.0f ms  ->  新 %.0f ms"
              % (max(r[1] for r in rows), max(r[2] for r in rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
