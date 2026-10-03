# -*- coding: utf-8 -*-
"""诊断：封面下载是否阻塞歌词上屏（_start_fetch worker 的真实时序）。

问题：worker 里先 fetch_lyrics 拿到歌词，然后才 http_get(cover_url, timeout=5)，
最后才 emit('fetched')。也就是说**歌词要等封面图下载完才显示**，
封面只是锦上添花，却成了阻塞主路径的同步步骤。
"""
import os, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lyrics_overlay as L

SONGS = [
    ("晴天", "周杰伦"),
    ("无所谓", "杨千嬅"),
    ("起风了", "买辣椒也用券"),
    ("夜曲", "周杰伦"),
    ("海阔天空", "Beyond"),
    ("光辉岁月", "Beyond"),
]


def timed_fetch(title, artist):
    """复刻 worker() 的真实时序，分别量 lyrics / cover / total。"""
    t0 = time.perf_counter()
    lines, words, cover_url, trans, singer_ok = L.fetch_lyrics(title, artist)
    t1 = time.perf_counter()
    cover_bytes = None
    if cover_url:
        try:
            cover_bytes = L.http_get(cover_url, timeout=5)
        except Exception as ex:
            cover_bytes = None
    t2 = time.perf_counter()
    return {
        "title": title, "artist": artist,
        "has_lyrics": bool(lines), "nwords": len(words or {}),
        "cover_url": cover_url, "has_cover_bytes": cover_bytes is not None,
        "cover_bytes": len(cover_bytes) if cover_bytes else 0,
        "t_lyrics": t1 - t0, "t_cover": t2 - t1, "t_total": t2 - t0,
    }


def main():
    print("=" * 78)
    print("诊断：封面下载是否阻塞歌词上屏")
    print("=" * 78)
    print("%-12s %-10s %5s %8s %8s %8s  %s" % (
        "歌", "歌手", "行数", "歌词ms", "封面ms", "合计ms", "封面字节"))
    print("-" * 78)
    rows = []
    for title, artist in SONGS:
        r = timed_fetch(title, artist)
        rows.append(r)
        print("%-12s %-10s %5d %8.0f %8.0f %8.0f  %d" % (
            r["title"], r["artist"], r["nwords"],
            r["t_lyrics"] * 1000, r["t_cover"] * 1000,
            r["t_total"] * 1000, r["cover_bytes"]))
    with_cover = [r for r in rows if r["cover_url"]]
    if with_cover:
        avg_cover = sum(r["t_cover"] for r in with_cover) / len(with_cover)
        max_cover = max(r["t_cover"] for r in with_cover)
        wasted = sum(r["t_cover"] for r in with_cover) * 1000
        print("-" * 78)
        print("有封面的歌：%d/%d" % (len(with_cover), len(rows)))
        print("封面下载平均耗时 %.0f ms，最大 %.0f ms" % (avg_cover * 1000, max_cover * 1000))
        print("→ 这些时间**全部花在等封面上，歌词早就拿到了**")
        print("→ 合计浪费 %.1f 秒" % (wasted / 1000))
    else:
        print("本次抽样没有歌带封面 URL，无法量化。")
    print("=" * 78)


if __name__ == "__main__":
    main()
