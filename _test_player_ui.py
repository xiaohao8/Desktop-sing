# -*- coding: utf-8 -*-
"""Player UI and listening-statistics regression tests.

Run with the project build environment:
    .buildenv312\\Scripts\\python.exe _test_player_ui.py
"""
import json
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _cfg_sandbox  # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

_tmp = tempfile.TemporaryDirectory(prefix="desktop-sing-player-test-")
os.environ["DESKTOP_SING_LISTEN_PATH"] = os.path.join(_tmp.name, "listening.json")
os.environ["DESKTOP_SING_COVERS_PATH"] = os.path.join(_tmp.name, "covers")

import lyrics_overlay as L  # noqa: E402
import lyrics_view as V  # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402


FAILS = []


def check(name, cond, detail=""):
    print(("  ok  - " if cond else "  FAIL- ") + name
          + ((" | " + str(detail)) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def seed(tracker, title, seconds, *, final=False, force=False):
    tracker.on_media({"title": title, "artist": "Test Artist",
                      "source": "test", "album": "ignored"})
    tracker._seconds = float(seconds)
    tracker._persisted_seconds = 0.0
    tracker._status = "PLAYING"
    tracker.flush(final=final, force=force)


app = QApplication.instance() or QApplication([])
L._load_fonts()
L.set_ui_lang("zh-CN")

# ---- ListeningStore / ListeningTracker ------------------------------------
path = os.path.join(_tmp.name, "tracker.json")
store = L.listening_store.ListeningStore(path)
enabled = [True]
tracker = L.listening_store.ListeningTracker(store, lambda: enabled[0])

seed(tracker, "Short", 10.0, final=True)
check("10 秒不落盘", not store.stats()["total_seconds"],
      store.stats())

seed(tracker, "Partial", 25.0)
stats = store.stats()
check("25 秒刷新后立即可见", stats["total_seconds"] == 25.0, stats)
check("刷新快照不计播放次数", stats["month_plays"] == 0, stats)

tracker.flush(final=False)
check("重复刷新不重复累计秒数", store.stats()["total_seconds"] == 25.0,
      store.stats())
tracker.flush(final=True)
stats = store.stats()
check("最终结算只计一次播放", stats["month_plays"] == 1, stats)
check("最终结算不重复累计秒数", stats["total_seconds"] == 25.0, stats)
tracker.flush(final=True)
check("重复最终结算无副作用", store.stats()["month_plays"] == 1,
      store.stats())

contract_store = L.listening_store.ListeningStore(
    os.path.join(_tmp.name, "contract.json"))
contract_cover = L.listening_store.save_cover(b"contract-cover")
contract_store.add_session("Contract Song", "Test Artist", seconds=40.0,
                           source="smtc-contract", duration=180.0,
                           position=32.0, cover_hash=contract_cover)
contract_track = contract_store.recent_tracks(1)[0]
check("历史 v2 输出会话来源与进度",
      contract_track["source"] == "smtc-contract"
      and contract_track["duration"] == 180.0
      and contract_track["position"] == 32.0,
      contract_track)
check("历史 v2 输出封面与续播 ID",
      contract_track["cover"] == contract_cover
      and contract_track["resume_id"]
      and "smtc-contract" in contract_track["resume_id"],
      contract_track)

legacy_path = os.path.join(_tmp.name, "legacy.json")
with open(legacy_path, "w", encoding="utf-8") as handle:
    json.dump({"v": 1, "sessions": [{
        "d": "2026-11-25", "k": "legacy|artist", "t": "Legacy Song",
        "a": "Test Artist", "s": 45.0, "n": 1, "h": 12, "last": time.time()
    }]}, handle, ensure_ascii=False)
legacy_store = L.listening_store.ListeningStore(legacy_path)
legacy_track = legacy_store.recent_tracks(1)[0]
check("旧历史惰性迁移且不可续播",
      legacy_store.data["v"] == 2
      and legacy_track["source"] == ""
      and legacy_track["cover"] == ""
      and legacy_track["resume_id"] == "",
      (legacy_store.data["v"], legacy_track))
check("封面缓存按内容键读写",
      L.listening_store.load_cover(contract_cover) == b"contract-cover"
      and L.listening_store.load_cover("0" * 64) == b"",
      contract_cover)

# Same-track SMTC metadata refreshes must not restart the session.
tracker.on_media({"title": "Stable", "artist": "Test Artist",
                  "source": "test"})
tracker._seconds = 18.0
tracker._status = "PLAYING"
for _ in range(4):
    tracker.on_media({"title": "Stable", "artist": "Test Artist",
                      "source": "test", "album": "metadata refresh"})
check("同曲元数据刷新不重置累计", tracker._seconds == 18.0,
      tracker._seconds)
tracker._seconds = 22.0
tracker.on_media({"title": "Next", "artist": "Test Artist",
                  "source": "test"})
check("切歌时最终结算上一首", store.stats()["month_plays"] == 2,
      store.stats())

# Disabling statistics must settle the current session first.
tracker.on_media({"title": "Disable", "artist": "Test Artist",
                  "source": "test"})
tracker._seconds = 31.0
tracker._status = "PLAYING"
enabled[0] = False
tracker.flush(final=True, force=True)
check("关闭统计前强制结算已听时长", store.stats()["total_seconds"] >= 78.0,
      store.stats())
check("关闭统计后本次播放计数一次", store.stats()["month_plays"] == 3,
      store.stats())
tracker.reset()
tracker.on_media({"title": "Ignored", "artist": "Test Artist",
                  "source": "test"})
tracker._seconds = 40.0
tracker._status = "PLAYING"
tracker.flush(final=True)
check("关闭统计后不再写入", "Ignored" not in
      [t["title"] for t in store.recent_tracks(20)],
      store.recent_tracks(20))
enabled[0] = True

# Clear then reset must not resurrect the in-memory session.
seed(tracker, "Before clear", 30.0)
tracker.flush(final=True, force=True)
store.clear()
tracker.reset()
tracker.flush(final=True)
check("清空后旧会话不回写", not store.recent_tracks(20),
      store.recent_tracks(20))

# ---- History formatting ---------------------------------------------------
hist_store = L.listening_store.ListeningStore(
    os.path.join(_tmp.name, "history.json"))
hist_store.add_session("Thirty", "Artist", seconds=30.0,
                       started_at=time.time(), plays=1, total_seconds=30.0)
history = V.HistoryPage(L._tr, lambda _t, _a: ([], {}))
history.set_tracks(hist_store.recent_tracks(10))
rows = history.findChildren(QPushButton)
row_text = "\n".join(b.text() for b in rows)
check("历史 30 秒显示秒而非 0 分钟",
      "30 秒" in row_text and "0 分钟" not in row_text, row_text)
check("历史显示一次播放", "1 次" in row_text, row_text)

# ---- Real main player construction ----------------------------------------
ov = L.LyricOverlay(L.MediaWatcher())
ov.song = {"title": "夜航西飞", "artist": "示例歌手", "source": "test",
           "duration": 240.0}
ov.lines = [[0.0, "灯光从窗边慢慢退去"], [6.0, "我把今天折进风里"],
            [12.0, "沿着没有名字的街道"], [18.0, "听见城市轻轻呼吸"]]
ov._trans_map = {0: "The lights fade slowly", 1: "I fold today into the wind"}
ov.duration = 240.0
ov.status = "PLAYING"
ov.anchor_pos = 8.0
ov.anchor_ts = time.monotonic()

player = V.MainPlayerWindow(ov)
player.resize(1260, 820)
player.show()
app.processEvents()
player._refresh_now(force=True)
player._timer.stop()
player.now.update_progress(72.0, 240.0, True)
app.processEvents()

check("主播放器窗口可构造", player.isVisible(), player.size())
check("窗口标题正确", "正在播放" in player.windowTitle(),
      player.windowTitle())
check("进度条挂在播放条下", player.now.slider.parent() is player.now.bar,
      type(player.now.slider.parent()).__name__)
check("进度条可见且有宽度", player.now.slider.isVisible()
      and player.now.slider.width() >= 80, player.now.slider.geometry())
check("进度条与播放条相交",
      player.now.slider.geometry().intersects(player.now.bar.rect()),
      (player.now.slider.geometry(), player.now.bar.rect()))
check("进度值已更新", player.now.slider.value() == 300,
      player.now.slider.value())
player._timer.start()

player.navigate("report")
app.processEvents()
check("听歌报告入口可用", player.stack.currentWidget() is player.report)
check("报告空态给出明确的 20 秒规则",
      player.report.empty.isVisible()
      and "20" in player.report.empty.text(), player.report.empty.text())
check("报告空态隐藏零值图表",
      not player.report.spark.isVisible()
      and not player.report.artist_card.isVisible()
      and not player.report.today.isVisible(),
      (player.report.spark.isVisible(), player.report.artist_card.isVisible(),
       player.report.today.isVisible()))
player.navigate("history")
app.processEvents()
check("播放历史入口可用", player.stack.currentWidget() is player.history)
check("历史空态同时说明统计门槛",
      "20" in player.history.d_lyrics.text(), player.history.d_lyrics.text())

player.navigate("settings")
check("设置入口可用", player.stack.currentWidget() is player.settings_page,
      type(player.stack.currentWidget()).__name__)

player.navigate("now")
player.toggle_immersive()
app.processEvents()
check("进入沉浸模式", player._immersive and not player.sidebar.isVisible(),
      player._immersive)
player.toggle_immersive()
app.processEvents()
check("退出沉浸模式", not player._immersive and player.sidebar.isVisible(),
      player._immersive)

player.enter_mini()
app.processEvents()
check("切换到迷你模式会隐藏主窗口", not player.isVisible())

# ---- Settings persistence -------------------------------------------------
panel = L.SettingsPanel(ov)
panel._on_listen_stats(False)
with open(L.CONFIG_PATH, encoding="utf-8") as f:
    saved = json.load(f)
check("关闭听歌统计会持久化", saved.get("listen_stats") is False,
      saved.get("listen_stats"))
panel._on_listen_stats(True)
with open(L.CONFIG_PATH, encoding="utf-8") as f:
    saved = json.load(f)
check("重新开启听歌统计会持久化", saved.get("listen_stats") is True,
      saved.get("listen_stats"))

player._timer.stop()
player.hide()
player.deleteLater()
panel.hide()
panel.deleteLater()
try:
    ov.hotkeys.unregister()
except Exception:
    pass
app.processEvents()

print("\nRESULT", "PASS" if not FAILS else "FAIL (%d)" % len(FAILS))
if FAILS:
    print("Failed:", ", ".join(FAILS))
sys.exit(0 if not FAILS else 1)
