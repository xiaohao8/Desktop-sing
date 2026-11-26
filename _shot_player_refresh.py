# -*- coding: utf-8 -*-
"""Capture the refreshed now-playing stage and immersive lyric mode."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lyrics_overlay as L  # noqa: E402
import lyrics_view as V  # noqa: E402
import ui_theme as UT  # noqa: E402

app = QApplication([])
L._load_fonts()
L.set_ui_lang("zh-CN")

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_player_refresh_shots")
os.makedirs(OUT, exist_ok=True)

song = {"title": "护花使者", "artist": "李克勤", "album": "Ever Last",
        "source": "QQMusic.exe", "cover": None, "duration": 198.0}
lines = [[0.0, "这晚在街中偶遇心中的她"], [6.0, "两脚决定不听叫唤跟她归家"],
         [12.0, "深宵的冷风 不准吹去她"], [18.0, "她那幽幽眼神快要对我说话"]]

for theme_id, appearance in (("ink", "dark"), ("celadon", "light")):
    theme = UT.THEMES[theme_id][appearance]
    stage = V.NowStage(L._tr)
    stage.setStyleSheet(UT.build_qss(theme, "main"))
    stage.set_theme(theme)
    stage.resize(1180, 760)
    stage.show()
    for _ in range(8):
        app.processEvents()
    stage.canvas.set_lyrics(lines, {}, song)
    stage.canvas.accent = QColor(theme.accent_fill)
    stage.canvas.set_playback(7.0, 1, True)
    stage.update_track(song, None)
    stage.update_progress(7.0, 198.0, True)
    stage.set_accent(QColor(theme.accent_fill))
    for _ in range(8):
        app.processEvents()
    stage.grab().save(os.path.join(OUT, "now_%s_%s.png" % (theme_id, appearance)))

    stage.resize(1600, 900)
    stage.set_immersive(True)
    for _ in range(8):
        app.processEvents()
    stage.grab().save(os.path.join(OUT, "immersive_%s_%s.png" % (theme_id, appearance)))
    stage.close()
    stage.deleteLater()

print("saved to", OUT)