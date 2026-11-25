# -*- coding: utf-8 -*-
"""Theme token structure, contrast, manager, and motion tests."""
import os
import re
import sys
import dataclasses

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


def _parse(color: str):
    color = color.strip()
    match = re.fullmatch(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", color)
    if match:
        red, green, blue, alpha = match.groups()
        return int(red), int(green), int(blue), float(alpha)
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", color)
    if match:
        value = match.group(1)
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 1.0
    raise ValueError(f"unsupported color: {color}")


def _composite(foreground: str, background: str):
    red, green, blue, alpha = _parse(foreground)
    back_red, back_green, back_blue, _ = _parse(background)
    return (
        red * alpha + back_red * (1 - alpha),
        green * alpha + back_green * (1 - alpha),
        blue * alpha + back_blue * (1 - alpha),
    )


def _luminance(rgb) -> float:
    linear = []
    for channel in rgb:
        value = channel / 255.0
        linear.append(
            value / 12.92 if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    first = _luminance(_composite(foreground, background))
    second = _luminance(_parse(background)[:3])
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


theme_fields = [field.name for field in fields(T.Theme)]
themes = [
    theme
    for variants in T.THEMES.values()
    for theme in variants.values()
]

ck("released themes", T.RELEASED_THEME_IDS == ("ink", "celadon"), T.RELEASED_THEME_IDS)
ck("amber is experimental", "amber" not in T.RELEASED_THEME_IDS, T.RELEASED_THEME_IDS)
ck("three themes x two appearances", len(themes) == 6, len(themes))

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
    ck(
        f"{theme.id}/{theme.appearance}: typography >= 12px",
        theme.fs_caption >= 12 and theme.fs_eyebrow >= 12 and theme.fs_body >= 13,
        (theme.fs_caption, theme.fs_eyebrow, theme.fs_body),
    )

for theme in themes:
    for foreground_name, backgrounds in (
        ("text", ("bg", "surface", "surface_sunken")),
        ("text_secondary", ("bg", "surface", "surface_sunken")),
        ("text_muted", ("bg", "surface", "surface_sunken")),
    ):
        for background_name in backgrounds:
            ratio = contrast(getattr(theme, foreground_name), getattr(theme, background_name))
            ck(
                f"{theme.id}/{theme.appearance}: {foreground_name}/{background_name} >= 4.5",
                ratio >= 4.5,
                round(ratio, 2),
            )

    ratio = contrast(theme.success, theme.surface_sunken)
    ck(
        f"{theme.id}/{theme.appearance}: success/surface_sunken >= 4.5",
        ratio >= 4.5,
        round(ratio, 2),
    )

    ratio = contrast(theme.text_disabled, theme.surface)
    ck(
        f"{theme.id}/{theme.appearance}: text_disabled/surface >= 3.0",
        ratio >= 3.0,
        round(ratio, 2),
    )

    ratio = contrast(theme.border_strong, theme.surface)
    ck(
        f"{theme.id}/{theme.appearance}: border_strong/surface >= 3.0",
        ratio >= 3.0,
        round(ratio, 2),
    )

    for background_name in ("bg", "surface"):
        ratio = contrast(theme.focus, getattr(theme, background_name))
        ck(
            f"{theme.id}/{theme.appearance}: focus/{background_name} >= 3.0",
            ratio >= 3.0,
            round(ratio, 2),
        )

    ck(
        f"{theme.id}/{theme.appearance}: accent_soft is translucent",
        theme.accent_soft.startswith("rgba("),
        theme.accent_soft,
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

bad_border = dataclasses.replace(
    T.THEMES["ink"]["light"], border_strong="rgba(27,26,24,.12)"
)
ck(
    "negative probe: weak border_strong detected",
    contrast(bad_border.border_strong, bad_border.surface) < 3.0,
    round(contrast(bad_border.border_strong, bad_border.surface), 2),
)
bad_muted = dataclasses.replace(T.THEMES["celadon"]["light"], text_muted="#87948C")
ck(
    "negative probe: low muted text detected",
    contrast(bad_muted.text_muted, bad_muted.surface_sunken) < 4.5,
    round(contrast(bad_muted.text_muted, bad_muted.surface_sunken), 2),
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
ck("manager default appearance mode", manager.appearance() == "system", manager.appearance())

emissions = []
manager.changed.connect(lambda theme: emissions.append(theme))
manager.set_theme("celadon")
ck("manager set theme", manager.current().id == "celadon", manager.current().id)
ck("manager emits once on change", len(emissions) == 1, len(emissions))
manager.set_theme("celadon")
ck("manager skips duplicate theme", len(emissions) == 1, len(emissions))

manager.set_appearance("system")
manager.system_appearance = lambda: "dark"
manager.refresh_system()
ck("manager follows system dark", manager.current().appearance == "dark",
   manager.current().appearance)
before_system = len(emissions)
manager.system_appearance = lambda: "light"
ck("manager follows system", manager.refresh_system().appearance == "light",
   manager.refresh_system().appearance)
ck("manager emits on system change", len(emissions) == before_system + 1, len(emissions))

manager.set_appearance("dark")
ck("manager explicit appearance", manager.current().appearance == "dark",
   manager.current().appearance)

before = len(emissions)
manager.set_reduce_motion(True)
ck("manager emits on reduce motion", len(emissions) == before + 1, len(emissions))
ck("manager reduce motion zeroes durations",
   manager.duration("m_fast") == 0 and manager.duration("m_base") == 0,
   (manager.duration("m_fast"), manager.duration("m_base")))
manager.set_reduce_motion(False)
ck("manager restores durations", manager.duration("m_base") == 180,
   manager.duration("m_base"))

original_system_animations = T.system_animations_enabled
T.system_animations_enabled = lambda: False
following = T.ThemeManager(reduce_motion=None)
ck("manager follows Windows animations", following.reduce_motion() is True,
   following.reduce_motion())
T.system_animations_enabled = original_system_animations

print("----", "FAIL: %d" % len(fails) if fails else "全部通过")
sys.exit(1 if fails else 0)



