# -*- coding: utf-8 -*-
"""Generate the settings-page screenshot matrix for the UI refresh review.

Usage:
    QT_SCALE_FACTOR=1.0  python _make_settings_matrix.py <outdir>
    QT_SCALE_FACTOR=1.5  python _make_settings_matrix.py <outdir>
    QT_SCALE_FACTOR=2.0  python _make_settings_matrix.py <outdir>
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _cfg_sandbox  # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False,
                   open_player_on_start=False,
                   theme_id="celadon", appearance="light")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lyrics_overlay as L  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.runtime import ApplicationRuntime  # noqa: E402

app = QApplication.instance() or QApplication([])
L._load_fonts()
L.set_ui_lang("zh-CN")

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_settings_matrix")
SCALE = os.environ.get("QT_SCALE_FACTOR", "1.0")
os.makedirs(OUT, exist_ok=True)

LANGS = ("zh-CN", "zh-TW", "en", "ja")
THEMES = ("ink", "celadon")
APPEARANCES = ("light", "dark")


class FakeWatcher(QObject):
    mediaChanged = Signal(object)
    ticked = Signal(float, float, str)

    def __init__(self):
        super().__init__()
        self.started = False
        self.activated = False

    def start(self):
        self.started = True

    def activate(self):
        self.activated = True


def pump(n=6):
    for _ in range(n):
        app.processEvents()


def scroll_top(page):
    sb = page.panel._scroll_area.verticalScrollBar()
    sb.setValue(0)
    pump()


def scroll_bottom(page):
    sb = page.panel._scroll_area.verticalScrollBar()
    sb.setValue(sb.maximum())
    pump()


context = AppContext.from_runtime(L, ["Desktop-sing.exe"])
context.config["open_player_on_start"] = True
runtime = ApplicationRuntime(context, watcher_factory=FakeWatcher)
runtime.start()
player = runtime.shell.open_player()
player.resize(1060, 680)
player.navigate("settings")
pump(10)

dpr = float(SCALE)
count = 0
for lang in LANGS:
    L.set_ui_lang(lang)
    player.retranslate_ui()
    player.navigate("settings")
    player.resize(1060, 680)
    pump(10)
    page = player.settings_page
    for theme_id in THEMES:
        for appearance in APPEARANCES:
            player._theme_manager.set_theme(theme_id)
            player._theme_manager.set_appearance(appearance)
            pump(8)
            for position in ("top", "bottom"):
                if position == "top":
                    scroll_top(page)
                else:
                    scroll_bottom(page)
                name = "%s_%s_%s_x%s_%s_settings.png" % (
                    lang, theme_id, appearance, SCALE, position)
                player.grab().save(os.path.join(OUT, name))
                count += 1
    print("lang %s done" % lang, flush=True)

# ---- suplemental shots (scale 1 only) ----
if SCALE in ("1", "1.0", "1"):
    L.set_ui_lang("zh-CN")
    player.retranslate_ui()
    player.navigate("settings")
    player.resize(1060, 680)
    pump(10)
    page = player.settings_page

    standalone = L.SettingsPanel(runtime.overlay)
    standalone.show()
    pump(8)
    standalone.grab().save(os.path.join(OUT, "standalone_panel_x1.png"))
    standalone.close()
    standalone.deleteLater()
    pump()
    count += 1

    for theme_id in THEMES:
        player._theme_manager.set_theme(theme_id)
        player._theme_manager.set_appearance("light")
        pump(6)
        button = page.appearance.swatch_buttons[theme_id]
        button.grab().save(os.path.join(OUT, "swatch_%s_selected_x1.png" % theme_id))
        other = page.appearance.swatch_buttons[
            "celadon" if theme_id == "ink" else "ink"]
        other.grab().save(os.path.join(OUT, "swatch_%s_idle_x1.png" % theme_id))
        count += 2

    switch = page.appearance.motion_switch
    switch.setChecked(True)
    pump(3)
    switch.grab().save(os.path.join(OUT, "motion_switch_on_x1.png"))
    switch.setChecked(False)
    pump(3)
    switch.grab().save(os.path.join(OUT, "motion_switch_off_x1.png"))
    count += 2

    page.appearance.swatch_buttons["ink"].setFocus(Qt.OtherFocusReason)
    pump(3)
    page.appearance.swatch_buttons["ink"].grab().save(
        os.path.join(OUT, "focus_theme_card_x1.png"))
    page.appearance.motion_switch.setFocus(Qt.OtherFocusReason)
    pump(3)
    page.appearance.motion_switch.grab().save(
        os.path.join(OUT, "focus_motion_switch_x1.png"))
    page.panel._sync_card.grab().save(
        os.path.join(OUT, "focus_sync_card_x1.png"))
    count += 3

player._timer.stop()
player.close()
runtime.overlay._timer.stop()
runtime.overlay.tray.hide()
runtime.overlay.hide()
app.processEvents()
print("saved", count, "screenshots to", OUT)