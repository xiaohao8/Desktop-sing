# -*- coding: utf-8 -*-
"""Before/after probe for the remaining theme P1 items.

Usage:
    python _probe_theme_p1.py --out runtime/theme-p1/before --dpr 1.0
    python _probe_theme_p1.py --out runtime/theme-p1/after --dpr 1.5 --matrix

The probe only reads product code.  It records the real widget pixels for:

* P1-08: the Ctrl+Alt+S "panel" action and whether it creates a visible panel.
* P1-09: startup theme without a MainPlayerWindow (tray QSS + standalone panel).
* P1-10: Segmented selected-text contrast on the selected pill.
* P1-11: progress-slider focus ring contrast at 0/50/100 for four themes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

THEME_CASES = (
    ("ink", "dark"),
    ("ink", "light"),
    ("celadon", "dark"),
    ("celadon", "light"),
)
LANGS = ("zh-CN", "en", "ja", "zh-TW")
VALUES = (0, 500, 1000)


def _channel(value: int) -> float:
    value = value / 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _lum(color) -> float:
    return (
        0.2126 * _channel(color.red())
        + 0.7152 * _channel(color.green())
        + 0.0722 * _channel(color.blue())
    )


def _contrast(first, second) -> float:
    high, low = sorted((_lum(first), _lum(second)), reverse=True)
    return round((high + 0.05) / (low + 0.05), 3)


def _save(image, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path))
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--dpr", default=os.environ.get("P1_DPR", "1.0"))
    parser.add_argument("--label", default="")
    parser.add_argument("--matrix", action="store_true")
    args = parser.parse_args()

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = str(args.dpr)

    import _cfg_sandbox

    _cfg_sandbox.begin(
        hotkeys=False,
        keepalive=False,
        idle_saver=False,
        open_player_on_start=False,
        theme_id="celadon",
        appearance="light",
    )

    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QApplication,
        QSlider,
        QStyle,
        QStyleOptionSlider,
        QWidget,
    )

    import lyrics_overlay as L
    import ui_theme as T

    app = QApplication.instance() or QApplication([])
    L._load_fonts()
    L.set_ui_lang("zh-CN")

    class FakeWatcher(QObject):
        mediaChanged = Signal(object)
        ticked = Signal(float, float, str)

        def start(self):
            pass

        def activate(self):
            pass

    overlay = L.LyricOverlay(FakeWatcher())
    app.processEvents()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "label": args.label,
        "dpr": args.dpr,
        "scale_factor": os.environ.get("QT_SCALE_FACTOR"),
        "screenshots": [],
        "p1_08": {},
        "p1_09": {},
        "p1_10": {},
        "p1_11": {},
    }

    # ---- P1-08: Ctrl+Alt+S panel action -----------------------------------
    standalone_returned = overlay._open_settings(standalone=True)
    overlay._on_hotkey("panel")
    app.processEvents()
    panel = overlay.panel
    report["p1_08"] = {
        "standalone_returned": bool(standalone_returned),
        "panel_created": panel is not None,
        "panel_visible": bool(panel is not None and panel.isVisible()),
        "fallback_player_created": overlay.main_player is not None,
    }

    # ---- P1-09: startup theme without MainPlayerWindow ---------------------
    manager = getattr(overlay, "theme_manager", None)
    theme = manager.current() if manager is not None else None
    tray_qss = overlay._tray_menu.styleSheet() if getattr(overlay, "_tray_menu", None) else ""
    if panel is None:
        panel = L.SettingsPanel(overlay)
    panel._fade.stop()
    panel._clear_fade()
    panel.resize(548, 760)
    panel.show()
    app.processEvents()
    panel._clear_fade()
    panel_qss = panel.styleSheet()
    expected = T.THEMES["celadon"]["light"]
    report["p1_09"] = {
        "main_player_created": overlay.main_player is not None,
        "manager_present": manager is not None,
        "current_theme": (
            manager.current().id + "/" + manager.current().appearance
            if manager is not None
            else None
        ),
        "tray_has_celadon_surface": (
            expected.surface_raised.lower() in tray_qss.lower()
        ),
        "tray_has_celadon_bg": expected.bg.lower() in tray_qss.lower(),
        "tray_has_celadon_text": expected.text.lower() in tray_qss.lower(),
        "tray_has_old_dark": "#15181f" in tray_qss.lower(),
        "panel_theme": (
            getattr(panel, "_theme").id + "/" + getattr(panel, "_theme").appearance
            if getattr(panel, "_theme", None) is not None
            else None
        ),
        "panel_has_celadon_bg": expected.bg.lower() in panel_qss.lower(),
        "panel_has_old_dark": "#0c0f15" in panel_qss.lower(),
    }
    report["screenshots"].append(
        _save(panel.grab(), out / "p1_09_standalone_settings.png")
    )
    panel.close()
    panel.deleteLater()
    app.processEvents()

    # ---- P1-10: Segmented selected text contrast --------------------------
    for theme_id, appearance in THEME_CASES:
        item = T.THEMES[theme_id][appearance]
        seg = L.Segmented(
            [("a", "AAAA"), ("b", "BBBB")], current="a", h=32
        )
        seg.set_theme(item)
        seg.set_accent(QColor(item.accent_fill))
        seg.resize(260, 32)
        seg.show()
        app.processEvents()
        image = seg.grab().toImage()
        scale = float(image.devicePixelRatio() or 1.0)
        def px(value):
            return int(round(value * scale))
        # Sample inside the selected pill, away from the centred label.
        backgrounds = [
            image.pixelColor(px(x), px(y))
            for x in (15, 22, 29)
            for y in range(8, 25)
        ]
        target = QColor(item.on_accent)
        best = None
        best_distance = 10**9
        for y in range(3, 29):
            for x in range(3, 127):
                pixel = image.pixelColor(px(x), px(y))
                distance = (
                    (pixel.red() - target.red()) ** 2
                    + (pixel.green() - target.green()) ** 2
                    + (pixel.blue() - target.blue()) ** 2
                )
                if distance < best_distance:
                    best = pixel
                    best_distance = distance
        key = f"{theme_id}/{appearance}"
        report["p1_10"][key] = {
            "on_accent": target.name(),
            "sample_text": best.name() if best is not None else None,
            "sample_background_worst": min(
                backgrounds, key=lambda color: _contrast(best, color)
            ).name(),
            "pixel_contrast": (
                min(_contrast(best, color) for color in backgrounds)
                if best is not None
                else 0.0
            ),
            "token_contrast_accent_fill": _contrast(
                target, QColor(item.accent_fill)
            ),
            "token_contrast_accent_pressed": _contrast(
                target, QColor(item.accent_pressed)
            ),
            "legacy_gradient_top_contrast": _contrast(
                target, QColor(item.accent_fill).lighter(124)
            ),
        }
        report["screenshots"].append(
            _save(
                image,
                out / f"p1_10_segmented_{theme_id}_{appearance}.png",
            )
        )
        seg.close()
        seg.deleteLater()
        app.processEvents()

    # ---- P1-11: progress slider focus ring at 0/50/100 --------------------
    class SliderHost(QWidget):
        def __init__(self, item, value):
            super().__init__()
            self.resize(460, 60)
            self.setObjectName("p1Host")
            self.setStyleSheet(
                "QWidget#p1Host { background: %s; }" % item.surface_raised
            )
            self.slider = QSlider(Qt.Horizontal, self)
            self.slider.setObjectName("progress")
            self.slider.setRange(0, 1000)
            self.slider.setValue(value)
            self.slider.setGeometry(20, 20, 420, 18)
            self.slider.setStyleSheet(T.build_qss(item, "main"))
            self.slider.setFocusPolicy(Qt.StrongFocus)
            self.show()
            self.activateWindow()
            self.slider.setFocus(Qt.OtherFocusReason)

    for theme_id, appearance in THEME_CASES:
        item = T.THEMES[theme_id][appearance]
        for value in VALUES:
            host = SliderHost(item, value)
            app.processEvents()
            host.slider.setFocus(Qt.OtherFocusReason)
            app.processEvents()
            image = host.grab().toImage()
            scale = float(image.devicePixelRatio() or 1.0)
            def px(value):
                return int(round(value * scale))
            option = QStyleOptionSlider()
            host.slider.initStyleOption(option)
            rect = host.slider.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderHandle,
                host.slider,
            )
            cx = px(20 + rect.center().x())
            cy = px(20 + rect.center().y())
            ring = image.pixelColor(cx, px(20 + rect.top() + 1))
            track = None
            if value > 0:
                track = image.pixelColor(
                    max(0, px(20 + rect.left() - 14)), cy
                )
            background = image.pixelColor(
                min(image.width() - 1, px(20 + rect.right() + 14)), cy
            )
            key = f"{theme_id}/{appearance}/{value}"
            report["p1_11"][key] = {
                "handle_focused": host.slider.hasFocus(),
                "handle_rect": [rect.x(), rect.y(), rect.width(), rect.height()],
                "ring": ring.name(),
                "track": track.name() if track is not None else None,
                "background": background.name(),
                "ring_track_contrast": (
                    _contrast(ring, track) if track is not None else None
                ),
                "ring_background_contrast": _contrast(ring, background),
                "legacy_focus_accent_contrast": _contrast(
                    QColor(item.focus), QColor(item.accent_fill)
                ),
            }
            report["screenshots"].append(
                _save(
                    image,
                    out
                    / f"p1_11_slider_{theme_id}_{appearance}_{value}.png",
                )
            )
            host.close()
            host.deleteLater()
            app.processEvents()

    # ---- Optional language x theme x DPR matrix ---------------------------
    if args.matrix:
        for lang in LANGS:
            L.set_ui_lang(lang)
            for theme_id, appearance in THEME_CASES:
                item = T.THEMES[theme_id][appearance]
                if manager is not None:
                    manager.set_theme(theme_id)
                    manager.set_appearance(appearance)
                settings = L.SettingsPanel(overlay)
                settings.set_theme(item)
                settings.resize(720, 760)
                settings.show()
                app.processEvents()
                settings._fade.stop()
                settings._clear_fade()
                report["screenshots"].append(
                    _save(
                        settings.grab(),
                        out
                        / f"settings_{lang}_{theme_id}_{appearance}.png",
                    )
                )
                settings._rt.stop()
                settings.close()
                settings.deleteLater()
                app.processEvents()

    (out / "probe.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    try:
        overlay._timer.stop()
        overlay._zorder_timer.stop()
        overlay._idle_timer.stop()
        overlay.hotkeys.unregister()
    except Exception:
        pass
    try:
        overlay.tray.hide()
    except Exception:
        pass
    overlay.close()
    overlay.deleteLater()
    app.processEvents()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
