# -*- coding: utf-8 -*-
"""SMTC 僵死桥接（WASAPI 音频真相源）单元测试。

背景：QQ 音乐偶发「SMTC 僵死」——音乐还在放，但 SMTC 把 playback_status 报成
PAUSED、timeline.position 停更（实测冻在 104.7s，last_updated_time 陈旧 134s）。
只信 SMTC 会让歌词与进度条一起冻死，用户看到「完全不同步，重新获取也没用」。

本测试覆盖三块：
  1) AUMID → 进程名的映射（桌面应用 / 打包应用两种形态）
  2) 桥接判定 `_smtc_zombie_bridge` 的真值表（关键是「真暂停」不能误判）
  3) 端到端：僵死期间歌词位置仍按时钟前进；音频停掉后立刻冻住
     以及 SMTC 恢复上报时 `_apply_tick` 能把偏差硬对齐吃掉

用法：.buildenv312\\Scripts\\python.exe -u _test_audio_bridge.py
"""
import os
import sys
import time
import types

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import lyrics_overlay as L                                     # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name,
                           ("  — " + detail) if detail else ""))


print("== 1. AUMID → 进程名 ==")
cases = [
    ("QQMusic.exe", "qqmusic"),
    ("C:\\Program Files\\QQMusic\\QQMusic.exe", "qqmusic"),
    ("SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify", "spotify"),
    ("CloudMusic.exe", "cloudmusic"),
    ("", ""),
]
for raw, want in cases:
    got = L._aumid_process(raw)
    check("%r -> %r" % (raw, want), got == want, "got=%r" % got)

print("== 2. 桥接判定真值表 ==")
music = "QQMusic.exe"
# (status, audio_alive, tracked, is_music, streak, 期望)
table = [
    ("PLAYING", False, True, True, 0, False),      # 正常播放：不需要桥接
    ("PLAYING", True, True, True, 5, False),       # 正常播放：也不需要
    ("PAUSED", False, True, True, 0, True and False),   # 真暂停（无声）→ 不能桥接
    ("PAUSED", True, True, True, 1, False),        # 刚探测到一次：防抖，先不动
    ("PAUSED", True, True, True, 2, True),         # 连续两次有声 → 判定僵死
    ("PAUSED", True, False, False, 9, False),      # 不认识的进程 → 不接管
    ("PAUSED", True, False, True, 9, True),        # 冷启动就遇上僵死的播放器 → 接管
    ("STOPPED", True, True, False, 3, True),       # 跟过的会话，状态再怪也接管
    ("PAUSED", True, True, True, 0, False),        # streak 归零（中间断过）→ 不接管
]
for st, alive, tracked, is_music, streak, want in table:
    got = L._smtc_zombie_bridge(st, alive, tracked, is_music, streak)
    check("status=%-8s alive=%-5s tracked=%-5s music=%-5s streak=%d -> %s"
          % (st, alive, tracked, is_music, streak, want), got == want, "got=%s" % got)

print("== 3. 端到端：僵死期间继续走字，音频停掉立即冻结 ==")
ov = types.SimpleNamespace(
    status="PLAYING", anchor_pos=104.7, anchor_ts=time.monotonic(),
    _last_tick_pos=104.7, _frozen_report=False, duration=229.7,
    _apply_pause_opacity=lambda: None)


def pos_now():
    # 与 LyricOverlay._current_pos 同语义：只有 PLAYING 才随时间外推
    if ov.status == "PLAYING":
        return ov.anchor_pos + (time.monotonic() - ov.anchor_ts)
    return ov.anchor_pos


# 3a 僵死：SMTC 反复报同一个 pos（104.7），桥接把 status 改判 PLAYING
for _ in range(6):
    L.LyricOverlay._apply_tick(ov, 104.7, 229.7, "PLAYING")
    time.sleep(0.2)
advanced = pos_now() - 104.7
check("僵死期间位置继续前进（1.2s 内前进 >0.8s）", advanced > 0.8,
      "advanced=%.2fs" % advanced)

# 3b 音频停掉：真实 PAUSED 到达 → 立刻锁死，不再往前走
L.LyricOverlay._apply_tick(ov, 110.0, 229.7, "PAUSED")
frozen = pos_now()
time.sleep(0.5)
check("真暂停后位置锁死不漂移", abs(pos_now() - frozen) < 1e-6,
      "pos=%.2f" % pos_now())

# 3c SMTC 恢复上报且位置大幅跳变 → 硬对齐（不留偏差）
L.LyricOverlay._apply_tick(ov, 160.0, 229.7, "PLAYING")
check("恢复上报后硬对齐到播放器值", abs(ov.anchor_pos - 160.0) < 1e-6,
      "anchor=%.2f" % ov.anchor_pos)

print("== 4. 真实 WASAPI 探针（独立线程 + 快照，调用线程零 COM） ==")
probe = L._AudioProbe()
# 探针跑在后台线程：等它的第一份快照（最多 5s）
table_real = {}
for _ in range(50):
    table_real = probe.active_processes()
    if table_real:
        break
    time.sleep(0.1)
check("能枚举到音频会话（>=1 个）", len(table_real) >= 1, "sessions=%d" % len(table_real))
check("状态值都是 bool", all(isinstance(v, bool) for v in table_real.values()))
check("不存在的进程返回 False", probe.is_active("NoSuchPlayer_zzz.exe") is False)
check("快照时间新鲜（<5s）", time.monotonic() - probe._stamp < 5.0)
# 调用线程没被 COM 初始化污染（2.0.3 的回归：STA 混进 SMTC 采集线程会挂死）
try:
    import ctypes
    hr = ctypes.OleDLL("ole32").CoInitializeEx(None, 0x2)
    check("调用线程 COM 状态未被探针污染（可再次初始化）", True, "hr=0x%x" % (hr & 0xFFFFFFFF))
except OSError as e:
    # RPC_E_CHANGED_MODE(0x80010106) = 本线程已被初始化成别的模型 = 被污染
    check("调用线程 COM 状态未被探针污染", (e.winerror & 0xFFFFFFFF) != 0x80010106,
          "hr=0x%x" % (e.winerror & 0xFFFFFFFF if e.winerror else 0))

print("=" * 60)
print("ALL PASS" if all(results) else "FAILED: %d / %d" % (results.count(False), len(results)))
sys.exit(0 if all(results) else 1)
