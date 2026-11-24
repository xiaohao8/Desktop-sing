# -*- coding: utf-8 -*-
"""Render Microsoft Store screenshots for the player-first UI.

The 2.0.x product opens a real player window. Older Store screenshots showed
only the desktop lyric overlay, so they no longer represent the first-run
experience. This script renders the current player window, immersive mode,
listening report, history page and mini bar at 1600x900.

Usage:
    .buildenv312\\Scripts\\python.exe store\\render_player_shots.py
    .buildenv312\\Scripts\\python.exe store\\render_player_shots.py --lang en
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import _cfg_sandbox  # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)
# Store screenshots must be deterministic and must never add demo sessions to
# the developer's real listening report.
_SHOT_TMP = tempfile.TemporaryDirectory(prefix="desktop-sing-store-shots-")
os.environ["DESKTOP_SING_LISTEN_PATH"] = os.path.join(_SHOT_TMP.name, "listening.json")

import lyrics_overlay as L  # noqa: E402
import lyrics_view as V  # noqa: E402
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = os.path.join(ROOT, "store", "out", "shots")
W, H = 1600, 900
LANG = "zh-CN"

DEMO = {
    "zh-CN": {
        "title": "夜航西飞", "artist": "演示歌手",
        "rows": [("夜航西飞", "演示歌手"), ("城市呼吸", "演示歌手"),
                 ("远处醒来", "演示歌手"), ("夜行列车", "演示歌手")],
        "lines": ["灯光从窗边慢慢退去", "我把今天折进风里",
                  "沿着没有名字的街道", "听见城市轻轻呼吸",
                  "如果夜色也有尽头", "就让我停在你的身后",
                  "远处的云正在醒来", "而我还不想回家"],
        "trans": ["The lights fade slowly by the window",
                  "I fold today into the wind",
                  "Along a street without a name",
                  "I hear the city breathe"],
    },
    "zh-TW": {
        "title": "夜航西飛", "artist": "示範歌手",
        "rows": [("夜航西飛", "示範歌手"), ("城市呼吸", "示範歌手"),
                 ("遠處醒來", "示範歌手"), ("夜行列車", "示範歌手")],
        "lines": ["燈光從窗邊慢慢退去", "我把今天摺進風裡",
                  "沿著沒有名字的街道", "聽見城市輕輕呼吸",
                  "如果夜色也有盡頭", "就讓我停在你的身後",
                  "遠處的雲正在醒來", "而我還不想回家"],
        "trans": ["The lights fade slowly by the window",
                  "I fold today into the wind",
                  "Along a street without a name",
                  "I hear the city breathe"],
    },
    "en": {
        "title": "Night Flight", "artist": "Demo Artist",
        "rows": [("Night Flight", "Demo Artist"), ("City Breath", "Demo Artist"),
                 ("Distant Waking", "Demo Artist"), ("Night Train", "Demo Artist")],
        "lines": ["The lights fade slowly by the window",
                  "I fold today into the wind",
                  "Along a street without a name",
                  "I hear the city breathe",
                  "If the night has an ending",
                  "Let me stay behind you",
                  "The distant clouds are waking",
                  "And I am not ready to go home"],
        "trans": ["灯光从窗边慢慢退去", "我把今天折进风里",
                  "沿着没有名字的街道", "听见城市轻轻呼吸"],
    },
    "ja": {
        "title": "夜のフライト", "artist": "デモアーティスト",
        "rows": [("夜のフライト", "デモアーティスト"), ("街の呼吸", "デモアーティスト"),
                 ("遠い目覚め", "デモアーティスト"), ("夜行列車", "デモアーティスト")],
        "lines": ["窓辺の灯りがゆっくり消えていく", "今日を風に折りたたむ",
                  "名前のない街を歩いて", "街の呼吸を聞く",
                  "夜にも終わりがあるなら", "あなたの後ろにいたい",
                  "遠くの雲が目を覚ます", "まだ家に帰りたくない"],
        "trans": ["The lights fade slowly by the window",
                  "I fold today into the wind",
                  "Along a street without a name",
                  "I hear the city breathe"],
    },
}


def _out_name(n: int, kind: str) -> str:
    suffix = "" if LANG == "zh-CN" else "-%s" % LANG
    return os.path.join(OUT, "player-%d-%s%s.png" % (n, kind, suffix))


def demo_cover() -> QPixmap:
    """Self-created artwork: no third-party album cover or lyrics."""
    pm = QPixmap(900, 900)
    pm.fill(QColor("#263238"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 900, 900)
    g.setColorAt(0.0, QColor("#8a4939"))
    g.setColorAt(0.45, QColor("#b85f43"))
    g.setColorAt(1.0, QColor("#1e2b33"))
    p.fillRect(0, 0, 900, 900, g)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 232, 205, 42))
    p.drawEllipse(95, 120, 520, 520)
    p.setBrush(QColor(20, 25, 30, 105))
    p.drawEllipse(430, 430, 620, 620)
    p.end()
    return pm


def new_overlay(demo):
    ov = L.LyricOverlay(L.MediaWatcher())
    L.set_ui_lang(LANG)
    ov.song = {"title": demo["title"], "artist": demo["artist"],
               "source": "demo", "duration": 237.0}
    ov.lines = [[float(i * 9), text] for i, text in enumerate(demo["lines"])]
    ov._trans_map = {i: text for i, text in enumerate(demo["trans"])}
    ov.duration = 237.0
    ov.status = "PLAYING"
    ov.anchor_pos = 20.0
    ov.anchor_ts = time.monotonic()
    ov.cover_pix = demo_cover()
    ov.accent1 = QColor("#ef704d")
    return ov


def _seed_history(ov):
    """Seed local demo sessions for the report/history screenshots."""
    now = time.time()
    samples = ((1460, 12, 0), (980, 8, 1), (640, 5, 2), (420, 3, 4))
    for (title, artist), (seconds, plays, days_ago) in zip(DEMO[LANG]["rows"], samples):
        ov.listen_store.add_session(
            title, artist, seconds=float(seconds),
            started_at=now - days_ago * 86400.0,
            plays=plays, total_seconds=float(seconds))


def _settle(app, rounds=5):
    for _ in range(rounds):
        app.processEvents()


def _save(widget, path):
    pix = widget.grab()
    if pix.isNull() or pix.width() < 1366 or pix.height() < 768:
        raise RuntimeError("invalid screenshot: %s" % path)
    _has_content(pix, path)
    pix.save(path)
    return path


def _has_content(pix, label):
    """Reject fully transparent / single-colour grabs from the offscreen platform."""
    img = pix.toImage()
    if img.isNull():
        raise RuntimeError("null screenshot: %s" % label)
    # Sample a grid; a real UI has many distinct pixels, while an empty grab is
    # one uniform colour. The threshold is deliberately low to keep dark stages.
    colors = set()
    for y in range(0, img.height(), max(1, img.height() // 40)):
        for x in range(0, img.width(), max(1, img.width() // 40)):
            c = img.pixelColor(x, y)
            colors.add((c.red() >> 3, c.green() >> 3, c.blue() >> 3, c.alpha() >> 5))
    if len(colors) < 6:
        raise RuntimeError("blank screenshot: %s (%d colours)" % (label, len(colors)))


def _save_mini(ov, path):
    """Place the real mini bar on a Store-sized, self-created backdrop."""
    # Capture at the overlay's natural card size. The offscreen platform does
    # not preserve an arbitrary window width here; a forced 1000 px grab comes
    # back empty. Scaling the real card keeps every pixel of the production UI.
    bar = ov.grab()
    if bar.isNull() or bar.width() < 400:
        raise RuntimeError("invalid mini bar capture")
    canvas = QPixmap(W, H)
    canvas.fill(QColor("#171a20"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0.0, QColor("#34272a"))
    g.setColorAt(0.48, QColor("#171a20"))
    g.setColorAt(1.0, QColor("#0c0e12"))
    p.fillRect(0, 0, W, H, g)

    cover = ov.cover_pix
    if cover is not None and not cover.isNull():
        scaled = cover.scaled(W, H, Qt.KeepAspectRatioByExpanding,
                              Qt.SmoothTransformation)
        src = QRectF((scaled.width() - W) / 2.0,
                     (scaled.height() - H) / 2.0, W, H)
        p.setOpacity(0.20)
        p.drawPixmap(QRectF(0, 0, W, H), scaled, src)
        p.setOpacity(1.0)

    target_w = min(1120, int(bar.width() * 1.35))
    target_h = max(1, int(bar.height() * target_w / float(bar.width())))
    shown = bar.scaled(target_w, target_h, Qt.KeepAspectRatio,
                       Qt.SmoothTransformation)
    x = (W - shown.width()) // 2
    y = (H - shown.height()) // 2
    p.drawPixmap(x, y, shown)
    p.setFont(V._pick_ui_font(13, bold=True))
    p.setPen(QColor(255, 248, 239, 190))
    p.drawText(QRectF(0, y + shown.height() + 22, W, 28),
               Qt.AlignHCenter | Qt.AlignTop,
               "Desktop-sing  ·  " + L._tr("桌面歌词条"))
    p.end()
    _has_content(canvas, path)
    if canvas.isNull() or not canvas.save(path):
        raise RuntimeError("failed to save mini screenshot: %s" % path)
    return path


def main():
    global LANG
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--lang" and i + 1 < len(args):
            LANG = args[i + 1]
        elif arg.startswith("--lang="):
            LANG = arg.split("=", 1)[1]
    if LANG not in DEMO:
        sys.exit("--lang only supports zh-CN / zh-TW / en / ja")

    os.makedirs(OUT, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    L._load_fonts()
    L.set_ui_lang(LANG)

    demo = DEMO[LANG]
    ov = new_overlay(demo)
    _seed_history(ov)
    player = V.MainPlayerWindow(ov)
    player.resize(W, H)
    player.show()
    _settle(app, 8)
    player._refresh_now(force=True)
    player.refresh_all()
    # refresh_all() calls update_track(), which resets the transport to 0:00.
    # Apply the demo playback state afterwards so the Store screenshot shows
    # a realistic mid-song position and a highlighted current lyric.
    player.now.update_progress(21.0, 237.0, True)
    player.now.canvas.set_playback(
        21.0, 2, True, accent=ov.accent1, cover=ov.cover_pix,
        song=ov.song, font_family=ov.font_family)
    _settle(app, 8)

    made = []
    made.append(_save(player, _out_name(1, "main")))

    player.navigate("report")
    _settle(app)
    made.append(_save(player, _out_name(2, "report")))

    player.navigate("history")
    _settle(app)
    tracks = ov.listen_store.recent_tracks(4)
    if tracks:
        player.history.show_track(tracks[0])
    _settle(app)
    made.append(_save(player, _out_name(3, "history")))

    player.navigate("now")
    # Offscreen showFullScreen() collapses to 800x800, which fails the Store
    # minimum. Render the immersive chrome at the same fixed 16:9 canvas.
    player._immersive = True
    player.sidebar.hide()
    player.titlebar.page_label.hide()
    player.now.immersive_btn.setText(player._tr("退出沉浸"))
    player.now.immersive_btn.adjustSize()
    player.resize(W, H)
    _settle(app, 8)
    made.append(_save(player, _out_name(4, "immersive")))
    player._immersive = False
    player.sidebar.show()
    player.titlebar.page_label.show()
    player.now.immersive_btn.setText(player._tr("沉浸歌词"))
    player.now.immersive_btn.adjustSize()
    _settle(app)

    ov.resize(1000, 260)
    ov._relayout()
    ov.show()
    _settle(app)
    mini_path = _out_name(5, "mini")
    made.append(_save_mini(ov, mini_path))

    player._timer.stop()
    player.close()
    ov._timer.stop()
    for timer_name in ("_zorder_timer", "_idle_timer"):
        timer = getattr(ov, timer_name, None)
        if timer is not None:
            timer.stop()
    try:
        ov.hotkeys.unregister()
    except Exception:
        pass
    ov.tray.hide()
    ov.hide()
    _settle(app)

    for path in made:
        print("  saved %s" % os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
