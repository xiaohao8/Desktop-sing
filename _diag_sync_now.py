# -*- coding: utf-8 -*-
"""现场诊断：一眼看清「歌词为什么不同步」。

同时打印三路信息：
  · SMTC（播放器报给系统的东西）——status / position / duration / 陈旧度
  · WASAPI 音频会话（进程到底有没有在出声）
  · 桥接结论（该不该信 SMTC；僵死时应用会改按本地时钟继续走字）

用法：.buildenv312\\Scripts\\python.exe -u _diag_sync_now.py [采样次数]
"""
import asyncio
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import lyrics_overlay as L                                     # noqa: E402

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 4


def ts(v):
    try:
        return v.total_seconds()
    except AttributeError:
        return float(v) / 10_000_000.0


async def main():
    if not L._load_smtc():
        print("SMTC 绑定缺失")
        return 1
    probe = L._AudioProbe()
    mgr = await L.MediaManager.request_async()
    for i in range(ROUNDS):
        print("---- 第 %d 次采样  %s" % (i + 1, time.strftime("%H:%M:%S")))
        sessions = list(mgr.get_sessions() or [])
        if not sessions:
            print("  （系统里没有任何媒体会话）")
        for s in sessions:
            sid = s.source_app_user_model_id or "?"
            st = L._status_name(s.get_playback_info().playback_status)
            tl = s.get_timeline_properties()
            pos, dur = ts(tl.position), ts(tl.end_time)
            age = L.MediaWatcher._lut_age(tl)
            try:
                prop = await s.try_get_media_properties_async()
                song = "%s - %s" % (prop.title, prop.artist)
            except Exception:
                song = "?"
            alive = probe.is_active(sid)
            bridge = L._smtc_zombie_bridge(st, alive and st != "PLAYING", True,
                                           L._is_music_aumid(sid), 2)
            print("  AUMID=%s  %s" % (sid, song))
            print("    SMTC   status=%-8s pos=%7.2f/%7.2f  陈旧度=%.1fs"
                  % (st, pos, dur, age))
            print("    WASAPI 该进程在出声=%s" % alive)
            if bridge:
                print("    → SMTC 僵死：应用会改按本地时钟继续走字（歌词不会卡死）")
            elif st != "PLAYING":
                print("    → 判定为真暂停/停止（歌词应停住，属正常）")
            else:
                print("    → 正常播放，按 SMTC 进度走")
        print()
        await asyncio.sleep(2)
    print("全部音频会话：", probe.active_processes())
    return 0


sys.exit(asyncio.run(main()))
