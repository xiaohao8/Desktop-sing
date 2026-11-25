# -*- coding: utf-8 -*-
"""Theme token structure, contrast, and manager smoke tests."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dataclasses import fields

from PySide6.QtGui import QGuiApplication

import ui_theme as T

app = QGuiApplication([])
fails = []


def ck(name, cond, extra=""):
    print(("  ok  - " if cond else "  FAIL- ") + name
          + (" | " + str(extra) if extra and not cond else ""))
    if not cond:
        fails.append(name)


def _hex_channel(value: str, start: int) -> float:
    return int(value[start : start + 2], 16) / 255.0


def _luminance(color: str) -> float:
    channels = [_hex_channel(color, index) for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    first = _luminance(foreground)
    second = _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


theme_fields = [field.name for field in fields(T.Theme)]
themes = [
    theme
    for variants in T.THEMES.values()
    for theme in variants.values()
]

for theme in themes:
    ck(
        f"{theme.id}/{theme.appearance}: fields",
        all(getattr(theme, field) not in ("", None) for field in theme_fields),
        {field: getattr(theme, field) for field in theme_fields
         if getattr(theme, field) in ("", None)},
    )
    ck(
        f"{theme.id}/{theme.appearance}: identity",
        theme.id in T.THEMES and theme.appearance in ("dark", "light"),
        (theme.id, theme.appearance),
    )

for theme in themes:
    for foreground_name, backgrounds in (
        ("text", ("bg", "surface")),
        ("text_secondary", ("bg", "surface")),
        ("text_muted", ("bg", "surface")),
    ):
        for background_name in backgrounds:
            ratio = contrast(getattr(theme, foreground_name), getattr(theme, background_name))
            ck(
                f"{theme.id}/{theme.appearance}: {foreground_name}/{background_name} >= 4.5",
                ratio >= 4.5,
                round(ratio, 2),
            )
    ratio = contrast(theme.on_accent, theme.accent_fill)
    ck(
        f"{theme.id}/{theme.appearance}: on_accent/accent_fill >= 4.5",
        ratio >= 4.5,
        round(ratio, 2),
    )
    for background_name in ("bg", "surface"):
        ratio = contrast(theme.accent_text, getattr(theme, background_name))
        ck(
            f"{theme.id}/{theme.appearance}: accent_text/{background_name} >= 3.0",
            ratio >= 3.0,
            round(ratio, 2),
        )
    for foreground_name in ("accent_hover", "accent_pressed"):
        ratio = contrast(getattr(theme, foreground_name), theme.on_accent)
        ck(
            f"{theme.id}/{theme.appearance}: {foreground_name}/on_accent >= 4.5",
            ratio >= 4.5,
            round(ratio, 2),
        )

print("---- accent contrast ----")
for theme in themes:
    fill_ratio = contrast(theme.on_accent, theme.accent_fill)
    hover_ratio = contrast(theme.accent_hover, theme.on_accent)
    pressed_ratio = contrast(theme.accent_pressed, theme.on_accent)
    print(
        f"{theme.id}/{theme.appearance}: fill={fill_ratio:.2f} "
        f"hover={hover_ratio:.2f} pressed={pressed_ratio:.2f}"
    )

sample = " ".join("{" + field + "}" for field in theme_fields)
for theme in themes:
    resolved = sample.format(**T.qss_tokens(theme))
    ck(
        f"{theme.id}/{theme.appearance}: qss tokens resolve",
        "{" not in resolved and "}" not in resolved,
        resolved,
    )

manager = T.ThemeManager()
ck("manager default theme", manager.current().id == "ink", manager.current().id)
ck("manager default appearance mode", manager._appearance == "system", manager._appearance)
manager.set_theme("celadon")
ck("manager set theme", manager.current().id == "celadon", manager.current().id)
manager.set_theme("ink")
manager.set_appearance("system")
manager.system_appearance = lambda: "light"
ck("manager follows system", manager.refresh_system().appearance == "light",
   manager.refresh_system().appearance)
manager.system_appearance = lambda: "dark"
ck("manager follows system back", manager.current().appearance == "dark",
   manager.current().appearance)

print("----", "FAIL: %d" % len(fails) if fails else "鍏ㄩ儴閫氳繃")
sys.exit(1 if fails else 0)



