# -*- coding: utf-8 -*-
"""Visual regression captures for the playlist page."""
import os
import json
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _cfg_sandbox  # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False,
                   open_player_on_start=False)

_tmp = tempfile.TemporaryDirectory(prefix="desktop-sing-playlist-visual-")
os.environ["DESKTOP_SING_LISTEN_PATH"] = os.path.join(_tmp.name,
                                                      "listening.json")

import lyrics_overlay as L  # noqa: E402
import lyrics_view as V  # noqa: E402
from app.lyrics_service import LyricsService  # noqa: E402
from PySide6.QtCore import Qt, qVersion  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


app = QApplication.instance() or QApplication([])
L._load_fonts()

overlay = L.LyricOverlay(L.MediaWatcher())
overlay.song = {"title": "夜航西飞", "artist": "示例歌手", "source": "test",
                "duration": 240.0}
overlay.duration = 240.0
overlay.status = "PLAYING"
overlay.current_resume_id = lambda: "current-session"

old_cache_dir = L.CACHE_DIR
L.CACHE_DIR = os.path.join(_tmp.name, "lyrics-cache")
os.makedirs(L.CACHE_DIR, exist_ok=True)
lyrics_service = LyricsService(L)
overlay.lyrics_service = lyrics_service
with open(lyrics_service.cache_path("夜航西飞", "示例歌手"), "w",
          encoding="utf-8") as handle:
    json.dump({"v": 4, "lines": [[0.0, "第一句"], [3.0, "第二句"]],
               "trans": [[0.1, "First"], [3.1, "Second"]],
               "words": {}, "sk": False, "roma": []},
              handle, ensure_ascii=False)

player = V.MainPlayerWindow(overlay)
player.show()
app.processEvents()

tracks = [
    {"title": "夜航西飞", "artist": "示例歌手", "duration": 240.0},
    {"title": "第二首历史", "artist": "示例歌手", "duration": 210.0},
    {"title": "Third Song", "artist": "示例歌手", "duration": 65.0},
    {"title": "Fourth Track", "artist": "示例歌手", "duration": 42.0},
]

outdir = os.path.join(ROOT, "_playlist_visual")
os.makedirs(outdir, exist_ok=True)

def _current_rows(page):
    return [page.list_lay.itemAt(index).widget()
            for index in range(page.list_lay.count())
            if isinstance(page.list_lay.itemAt(index).widget(),
                          V.PlaylistRowButton)]

scale_text = os.environ.get("PLAYLIST_P1_SCALE", "1.0")
p1_root = os.path.join(tempfile.gettempdir(), "dl208_audit", "playlist_p1",
                       "after_scale_" + scale_text.replace(".", "p"))
os.makedirs(p1_root, exist_ok=True)
p1_checks = {
    "scale": scale_text,
    "device_pixel_ratio": app.primaryScreen().devicePixelRatio(),
    "qt_version": qVersion(),
    "languages": {},
}

for lang in ("zh-CN", "en", "ja", "zh-TW"):
    L.set_ui_lang(lang)
    player.retranslate_ui()
    for width, height in ((1440, 900), (1280, 800), (1024, 700)):
        player.resize(width, height)
        player.navigate("history")
        app.processEvents()

        player.history.set_loading()
        app.processEvents()
        player.grab().save(os.path.join(
            outdir, "%s_%dx%d_loading.png" % (lang, width, height)))

        player.history.set_tracks([])
        app.processEvents()
        player.grab().save(os.path.join(
            outdir, "%s_%dx%d_empty.png" % (lang, width, height)))

        player.playlist.set_tracks(tracks)
        app.processEvents()
        player.grab().save(os.path.join(
            outdir, "%s_%dx%d_tracks.png" % (lang, width, height)))

        rows = _current_rows(player.playlist)
        rows[0].click()
        app.processEvents()
        player.navigate("history")
        app.processEvents()
        player.grab().save(os.path.join(
            outdir, "%s_%dx%d_selected.png" % (lang, width, height)))

        player.playlist.set_error("测试错误")
        app.processEvents()
        player.grab().save(os.path.join(
            outdir, "%s_%dx%d_error.png" % (lang, width, height)))

for lang in ("zh-CN", "en", "ja", "zh-TW"):
    player.show()
    player.resize(1060, 680)
    app.processEvents()
    L.set_ui_lang(lang)
    player.retranslate_ui()
    player.navigate("history")
    app.processEvents()

    p1_tracks = [
        {"title": "夜航西飞", "artist": "示例歌手", "duration": 240.0},
        {"title": "Unmatched Track", "artist": "示例歌手", "duration": 180.0},
        {"title": "L" * 120, "artist": "A" * 90, "duration": 96.0},
    ]
    player.playlist.set_tracks(p1_tracks)
    app.processEvents()
    player.grab().save(os.path.join(
        p1_root, "%s_1060x680_success.png" % lang))

    player.playlist.set_loading()
    app.processEvents()
    loading_cancel_visible = player.playlist.cancel_btn.isVisible()
    player.grab().save(os.path.join(
        p1_root, "%s_1060x680_loading_cancel.png" % lang))

    player.playlist.set_tracks(p1_tracks)
    rows = _current_rows(player.playlist)
    rows[0].click()
    app.processEvents()
    selected_after_click = rows[0].isChecked()
    player.navigate("history")
    app.processEvents()
    rows = _current_rows(player.playlist)
    player.grab().save(os.path.join(
        p1_root, "%s_1060x680_selected.png" % lang))

    rows[1].click()
    app.processEvents()
    player.grab().save(os.path.join(
        p1_root, "%s_1060x680_unmatched_now.png" % lang))
    player.navigate("history")
    app.processEvents()
    rows = _current_rows(player.playlist)
    rows[2].setFocus()
    app.processEvents()
    QTest.keyClick(rows[2], Qt.Key_Return)
    app.processEvents()
    player.grab().save(os.path.join(
        p1_root, "%s_1060x680_enter_activation.png" % lang))
    player.navigate("history")
    app.processEvents()
    rows = _current_rows(player.playlist)
    player.playlist.set_tracks([p1_tracks[2]])
    app.processEvents()
    long_rows = _current_rows(player.playlist)
    player.grab().save(os.path.join(
        p1_root, "%s_1060x680_long_metadata.png" % lang))

    p1_checks["languages"][lang] = {
        "selected": selected_after_click,
        "selected_after_click": selected_after_click,
        "loading_cancel_visible": loading_cancel_visible,
        "success": player.playlist.success.text(),
        "unmatched_empty": player.now.canvas.empty_message_key,
        "enter_selected_long": rows[2].isChecked(),
        "long_title_tooltip": bool(long_rows[0].title.toolTip()),
        "long_artist_tooltip": bool(long_rows[0].artist.toolTip()),
        "url_accessible_name": player.playlist.url_input.accessibleName(),
        "url_accessible_description":
            player.playlist.url_input.accessibleDescription(),
    }
    player.hide()

with open(os.path.join(p1_root, "p1_checks.json"), "w",
          encoding="utf-8") as handle:
    json.dump(p1_checks, handle, ensure_ascii=False, indent=2)

player._timer.stop()
player.close()
overlay._timer.stop()
for timer_name in ("_zorder_timer", "_idle_timer"):
    timer = getattr(overlay, timer_name, None)
    if timer is not None:
        timer.stop()
try:
    overlay.hotkeys.unregister()
except Exception:
    pass
overlay.tray.hide()
overlay.hide()
overlay.deleteLater()
L.CACHE_DIR = old_cache_dir
app.processEvents()

files = sorted(os.listdir(outdir))
print("history visual captures:", len(files))
for name in files:
    print(name)
p1_files = sorted(name for name in os.listdir(p1_root)
                  if name.endswith(".png"))
print("playlist p1 evidence:", len(p1_files), p1_root)
for name in p1_files:
    print(name)
