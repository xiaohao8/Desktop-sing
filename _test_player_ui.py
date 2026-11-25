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

import lyrics_overlay as L  # noqa: E402
import lyrics_view as V  # noqa: E402
from app.lyrics_service import LyricsService  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402


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

# ---- Playlist metadata -----------------------------------------------------
sample_playlist = "\n".join((
    "#EXTM3U",
    "#EXTINF:225,示例歌手 - 示例曲目",
    "https://example.com/sample.mp3",
    "02 - Second.mp3",
))
playlist_tracks = V._parse_m3u(sample_playlist)
check("M3U 只解析元数据",
      len(playlist_tracks) == 2
      and playlist_tracks[0]["title"] == "示例曲目"
      and playlist_tracks[0]["artist"] == "示例歌手"
      and playlist_tracks[0]["duration"] == 225.0
      and "audio_bytes" not in playlist_tracks[0],
      playlist_tracks)
check("M3U 按曲名歌手去重",
      len(V._parse_m3u(
          "#EXTM3U\n"
          "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/a.mp3\n"
          "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/b.mp3"
      )) == 1,
      V._parse_m3u("#EXTM3U\n"
                   "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/a.mp3\n"
                   "#EXTINF:225,示例歌手 - 示例曲目\nhttps://example.com/b.mp3"))
check("纯文本不解析为曲目", V._parse_m3u("这不是歌单") == [],
      V._parse_m3u("这不是歌单"))
check("歌单链接拒绝本地地址",
      not V._playlist_host_is_public("localhost")
      and not V._playlist_host_is_public("127.0.0.1"),
      (V._playlist_host_is_public("localhost"),
       V._playlist_host_is_public("127.0.0.1")))
check("私网与保留地址全部拒绝",
      not V._playlist_public_addresses("127.0.0.1")
      and not V._playlist_public_addresses("169.254.169.254")
      and not V._playlist_public_addresses("0.0.0.0"),
      (V._playlist_public_addresses("127.0.0.1"),
       V._playlist_public_addresses("169.254.169.254"),
       V._playlist_public_addresses("0.0.0.0")))
check("平台链接直接拒绝",
      V._playlist_is_platform_url("music.163.com")
      and V._playlist_is_platform_url("y.qq.com")
      and not V._playlist_is_platform_url("example.com"),
      (V._playlist_is_platform_url("music.163.com"),
       V._playlist_is_platform_url("y.qq.com"),
       V._playlist_is_platform_url("example.com")))

fetch_results = []
fetch_failures = []
fetch_thread = V.PlaylistFetchThread("https://example.com/playlist.m3u8")
fetch_thread.completed.connect(fetch_results.append)
fetch_thread.failed.connect(fetch_failures.append)
original_fetch = V._fetch_playlist_bytes
V._fetch_playlist_bytes = lambda url: sample_playlist.encode("utf-8")
try:
    fetch_thread.run()
finally:
    V._fetch_playlist_bytes = original_fetch
app.processEvents()
check("歌单 URL 导入线程可完成",
      fetch_results == [playlist_tracks]
      and not fetch_failures,
      (fetch_results, fetch_failures))

class _RedirectResponse:
    def __init__(self, status, headers):
        self.status = status
        self.headers = headers
    def getheader(self, name):
        return self.headers.get(name)
    def read(self, count=-1):
        return b""

class _RedirectConnection:
    requests = []
    def __init__(self, *args, **kwargs):
        self.pinned_ip = ""
    def request(self, method, path, headers=None):
        _RedirectConnection.requests.append(path)
    def getresponse(self):
        if len(_RedirectConnection.requests) == 1:
            return _RedirectResponse(302,
                                     {"Location": "http://127.0.0.1/x.m3u"})
        return _RedirectResponse(200, {})
    def close(self):
        pass

original_pinned_connection = V._PinnedHTTPSConnection
_RedirectConnection.requests.clear()
V._PinnedHTTPSConnection = _RedirectConnection
redirect_failure = ""
try:
    try:
        V._fetch_playlist_bytes("https://example.com/redirect.m3u")
    except Exception as exc:
        redirect_failure = str(exc)
finally:
    V._PinnedHTTPSConnection = original_pinned_connection
check("重定向到私网被拒绝",
      redirect_failure == "private-playlist-host"
      and _RedirectConnection.requests == ["/redirect.m3u"],
      (redirect_failure, _RedirectConnection.requests))

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
ov.current_resume_id = lambda: ""

lyrics_cache_dir = tempfile.mkdtemp(prefix="desktop-sing-lyrics-cache-")
old_cache_dir = L.CACHE_DIR
L.CACHE_DIR = lyrics_cache_dir
lyrics_service = LyricsService(L)
ov.lyrics_service = lyrics_service
with open(lyrics_service.cache_path("示例曲目", "示例歌手"), "w",
          encoding="utf-8") as handle:
    json.dump({"v": 4, "lines": [[0.0, "第一句"], [3.0, "第二句"]],
               "trans": [[0.1, "First"], [3.1, "Second"]],
               "words": {}, "sk": False, "roma": []},
              handle, ensure_ascii=False)

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
player.playlist.refresh()
app.processEvents()

def current_playlist_rows():
    return [player.playlist.list_lay.itemAt(index).widget()
            for index in range(player.playlist.list_lay.count())
            if isinstance(player.playlist.list_lay.itemAt(index).widget(),
                          V.PlaylistRowButton)]

check("URL 输入具备无障碍名称与说明",
      player.playlist.url_input.accessibleName()
      and player.playlist.url_input.accessibleDescription(),
      (player.playlist.url_input.accessibleName(),
       player.playlist.url_input.accessibleDescription()))
playlist_tracks = [{"title": "示例曲目", "artist": "示例歌手",
                    "duration": 225.0, "source": "https://example.com/x.mp3"}]
player.playlist.set_loading()
app.processEvents()
check("歌单加载态互斥", not player.playlist.import_btn.isEnabled()
      and player.playlist.list_lay.count() > 0
      and not player.playlist.error.isVisible(), player.playlist._state)
check("加载态显示取消",
      player.playlist.cancel_btn.isVisible()
      and player.playlist.cancel_btn.isEnabled(),
      (player.playlist.cancel_btn.isVisible(),
       player.playlist.cancel_btn.isEnabled()))
player.playlist._cancelled = True
player.playlist._cancel_import()
app.processEvents()
check("取消导入立即恢复空态",
      player.playlist._state == "empty"
      and player.playlist._tracks == []
      and not player.playlist.cancel_btn.isVisible(),
      (player.playlist._state, player.playlist._tracks,
       player.playlist.cancel_btn.isVisible()))
player.playlist._on_fetch_completed(playlist_tracks)
app.processEvents()
check("取消导入忽略线程结果",
      player.playlist._state == "empty"
      and player.playlist._tracks == []
      and not player.playlist.cancel_btn.isVisible(),
      (player.playlist._state, player.playlist._tracks,
       player.playlist.cancel_btn.isVisible()))
player.playlist.set_error("测试错误")
app.processEvents()
check("歌单错误态可见", player.playlist.error.isVisible()
      and player.playlist._state == "error"
      and player.playlist.url_input.property("error") == "1",
      (player.playlist._state, player.playlist.url_input.property("error")))
player.playlist.set_tracks([])
app.processEvents()
check("歌单空态可见", player.playlist._state == "empty",
      player.playlist._state)
player.playlist.set_tracks(playlist_tracks)
app.processEvents()
playlist_rows = current_playlist_rows()
check("歌单行可构造", len(playlist_rows) == 1
      and playlist_rows[0].title.text() == "示例曲目", playlist_rows)
check("本地歌词缓存行显示已就绪",
      playlist_rows[0].status.property("matched") == "1"
      and "歌词已就绪" in playlist_rows[0].status.text()
      and playlist_rows[0].status.text().startswith("✓"),
      playlist_rows[0].status.text())
check("成功态显示导入数量",
      player.playlist.success.isVisible()
      and player.playlist.success.text() == "已导入 1 首曲目",
      player.playlist.success.text())
selected_tracks = []
player.playlist.track_selected.connect(selected_tracks.append)
playlist_rows[0].click()
app.processEvents()
check("点击曲目进入歌词页",
      player.stack.currentWidget() is player.now
      and selected_tracks == playlist_tracks
      and player._playlist_track == playlist_tracks[0],
      (player.stack.currentWidget(), selected_tracks, player._playlist_track))
player.grab().save("_player_playlist_track_opened.png")
player.navigate("history")
app.processEvents()
playlist_rows = player.playlist.findChildren(V.PlaylistRowButton)
check("选中曲目状态保持", playlist_rows[0].isChecked(),
      playlist_rows[0].isChecked())
player.grab().save("_player_playlist_selected.png")

playlist_tracks = [
    playlist_tracks[0],
    {"title": "Unmatched Track", "artist": "示例歌手", "duration": 180.0,
     "source": "https://example.com/unmatched.mp3"},
    {"title": "L" * 120, "artist": "A" * 90, "duration": 96.0,
     "source": "https://example.com/long.mp3"},
]
player.playlist.set_tracks(playlist_tracks)
app.processEvents()
playlist_rows = current_playlist_rows()
playlist_rows[1].click()
app.processEvents()
check("点击后当前行保持选中",
      playlist_rows[1].isChecked()
      and player.playlist._selected_track == playlist_tracks[1],
      (playlist_rows[1].isChecked(), player.playlist._selected_track))
player.navigate("history")
app.processEvents()
playlist_rows = current_playlist_rows()
check("行选择强制单选",
      playlist_rows[1].isChecked()
      and not playlist_rows[0].isChecked()
      and not playlist_rows[2].isChecked(),
      [row.isChecked() for row in playlist_rows])
playlist_rows[1].click()
app.processEvents()
player.navigate("history")
app.processEvents()
playlist_rows = current_playlist_rows()
check("重复点击不清除选中", playlist_rows[1].isChecked(),
      [row.isChecked() for row in playlist_rows])
check("超长元数据保留全文并提示",
      playlist_rows[2].title.toolTip() == playlist_tracks[2]["title"]
      and playlist_rows[2].artist.toolTip() == playlist_tracks[2]["artist"]
      and playlist_tracks[2]["title"] in playlist_rows[2].accessibleName()
      and playlist_tracks[2]["artist"] in playlist_rows[2].accessibleName(),
      (playlist_rows[2].title.toolTip(),
       playlist_rows[2].accessibleName()))
playlist_rows[2].setFocus()
app.processEvents()
QTest.keyClick(playlist_rows[2], Qt.Key_Return)
app.processEvents()
check("回车激活歌单行",
      player.stack.currentWidget() is player.now
      and playlist_rows[2].isChecked()
      and selected_tracks[-1] == playlist_tracks[2],
      (player.stack.currentWidget(), [row.isChecked() for row in playlist_rows],
       selected_tracks[-1]))
check("未匹配曲目进入明确空态",
      player.now.canvas.empty_message_key == "未找到本地歌词"
      and player.now.canvas.empty_description_key == "请添加本地歌词文件后再试。",
      (player.now.canvas.empty_message_key,
       player.now.canvas.empty_description_key))
playlist_rows[0].click()
app.processEvents()
player.navigate("history")
app.processEvents()
playlist_rows = current_playlist_rows()
check("切换行后旧行取消选中",
      playlist_rows[0].isChecked() and not playlist_rows[1].isChecked()
      and not playlist_rows[2].isChecked(),
      [row.isChecked() for row in playlist_rows])
check("歌单页入口可用", player.stack.currentWidget() is player.playlist
      or player.stack.currentWidget() is player.now)

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

# ---- Language switch refreshes brand / immersive / stage eyebrow -----------
def _has_cjk(text):
    for ch in text or "":
        code = ord(ch)
        if 0x2E80 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF:
            return True
    return False


L.set_ui_lang("en")
player.retranslate_ui()
app.processEvents()
check("切 en 后窗口标题无中文",
      "Desktop-sing" in player.windowTitle()
      and not _has_cjk(player.windowTitle()), player.windowTitle())
check("切 en 后侧栏品牌", player.sidebar.brand_name.text() == "Desktop-sing",
      player.sidebar.brand_name.text())
check("切 en 后沉浸按钮", player.now.immersive_btn.text() == "Immersive lyrics",
      player.now.immersive_btn.text())
check("切 en 后舞台 eyebrow", player.now.source.text() == "Now playing",
      player.now.source.text())
L.set_ui_lang("ja")
player.retranslate_ui()
app.processEvents()
check("切 ja 后沉浸按钮", player.now.immersive_btn.text() == "没入歌詞",
      player.now.immersive_btn.text())
check("切 ja 后舞台 eyebrow", player.now.source.text() == "再生中",
      player.now.source.text())
player.now.update_track({"title": "夜航西飞", "artist": "示例歌手",
                         "duration": 240.0}, None)
L.set_ui_lang("en")
player.retranslate_ui()
app.processEvents()
check("有曲目时切语言不覆盖歌名",
      player.now.title.text() == "夜航西飞"
      and player.now.track_title.text() == "夜航西飞",
      (player.now.title.text(), player.now.track_title.text()))
L.set_ui_lang("zh-CN")
player.retranslate_ui()
app.processEvents()

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
