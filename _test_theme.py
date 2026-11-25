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
    surfaces = ("bg", "surface", "surface_raised", "surface_sunken", "surface_hover")
    for foreground_name in (
        "text", "text_secondary", "text_muted", "success", "warning", "danger",
    ):
        for background_name in surfaces:
            ratio = contrast(getattr(theme, foreground_name), getattr(theme, background_name))
            ck(
                f"{theme.id}/{theme.appearance}: {foreground_name}/{background_name} >= 4.5",
                ratio >= 4.5,
                round(ratio, 2),
            )

    for foreground_name in ("text_disabled", "border_strong", "focus"):
        for background_name in surfaces:
            ratio = contrast(getattr(theme, foreground_name), getattr(theme, background_name))
            ck(
                f"{theme.id}/{theme.appearance}: {foreground_name}/{background_name} >= 3.0",
                ratio >= 3.0,
                round(ratio, 2),
            )

    for background_name in ("surface", "surface_raised"):
        ratio = contrast(theme.scrollbar_handle, getattr(theme, background_name))
        ck(
            f"{theme.id}/{theme.appearance}: scrollbar_handle/{background_name} >= 3.0",
            ratio >= 3.0,
            round(ratio, 2),
        )

    ratio = contrast(theme.grip_dot, theme.surface)
    ck(
        f"{theme.id}/{theme.appearance}: grip_dot/surface >= 3.0",
        ratio >= 3.0,
        round(ratio, 2),
    )

    ratio = max(contrast(theme.control_handle_fill, theme.surface_sunken),
                contrast(theme.control_handle_outline, theme.surface_sunken))
    ck(
        f"{theme.id}/{theme.appearance}: handle visible on groove (0%) >= 3.0",
        ratio >= 3.0,
        round(ratio, 2),
    )
    ratio = max(contrast(theme.control_handle_fill, theme.accent_fill),
                contrast(theme.control_handle_outline, theme.accent_fill))
    ck(
        f"{theme.id}/{theme.appearance}: handle visible on filled track (100%) >= 3.0",
        ratio >= 3.0,
        round(ratio, 2),
    )
    ratio = contrast(theme.control_handle_fill, theme.control_handle_outline)
    ck(
        f"{theme.id}/{theme.appearance}: handle dual ring (50%) >= 3.0",
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
bad_grip = dataclasses.replace(
    T.THEMES["ink"]["light"], grip_dot="rgba(255,255,255,.36)"
)
ck(
    "negative probe: white grip dot on light detected",
    contrast(bad_grip.grip_dot, bad_grip.surface) < 3.0,
    round(contrast(bad_grip.grip_dot, bad_grip.surface), 2),
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

print("---- build_qss ----")
placeholder_re = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")
key_selectors = ("#shell", "#titlebar", "#sidebar", "#playlistPage",
                 "#settingsPage", "#playbar", "#appearanceSeg", "#themeSwatch",
                 "#reportScroll", "#reportBody", "#artistMeta", "#stage")
overlay_selectors = ("QMenu", "QMessageBox", "QDialog", "#wdtitle")
main_outputs = {}
for theme in themes:
    qss = T.build_qss(theme, "main")
    main_outputs[(theme.id, theme.appearance)] = qss
    ck(f"{theme.id}/{theme.appearance}: main qss no placeholders",
       not placeholder_re.findall(qss),
       placeholder_re.findall(qss)[:5])
    ck(f"{theme.id}/{theme.appearance}: main qss selectors",
       all(sel in qss for sel in key_selectors),
       [sel for sel in key_selectors if sel not in qss])
    ck(f"{theme.id}/{theme.appearance}: main qss uses scrollbar token",
       theme.scrollbar_handle in qss, theme.scrollbar_handle)
    ck(f"{theme.id}/{theme.appearance}: main qss has no 11px text",
       "font-size: 11px" not in qss)
    ck(f"{theme.id}/{theme.appearance}: main qss uses dual handle tokens",
       theme.control_handle_fill in qss and theme.control_handle_outline in qss)
    ov = T.build_qss(theme, "overlay")
    ck(f"{theme.id}/{theme.appearance}: overlay qss no placeholders",
       not placeholder_re.findall(ov),
       placeholder_re.findall(ov)[:5])
    ck(f"{theme.id}/{theme.appearance}: overlay qss selectors",
       all(sel in ov for sel in overlay_selectors),
       [sel for sel in overlay_selectors if sel not in ov])
    ck(f"{theme.id}/{theme.appearance}: overlay qss has no 11px text",
       "font-size: 11px" not in ov)
    ck(f"{theme.id}/{theme.appearance}: overlay qss has button focus",
       "QPushButton:focus" in ov)

for theme_id in T.THEMES:
    ck(f"{theme_id}: light/dark main qss differ",
       main_outputs[(theme_id, "light")] != main_outputs[(theme_id, "dark")])

try:
    T.build_qss(themes[0], "bogus")
    ck("unknown scope rejected", False)
except ValueError:
    ck("unknown scope rejected", True)
try:
    T.ThemeManager(theme_id="amber")
    rejected_experimental = False
except ValueError:
    rejected_experimental = True
ck("manager rejects experimental theme by default", rejected_experimental)

try:
    manager.set_theme("amber")
    rejected_set_experimental = False
except ValueError:
    rejected_set_experimental = True
ck("set_theme rejects experimental theme by default", rejected_set_experimental)
ck("manager keeps released theme after rejection", manager.current().id == "celadon",
   manager.current().id)

experimental = T.ThemeManager(theme_id="amber", allow_experimental=True)
ck("manager allows experimental when opted in", experimental.current().id == "amber",
   experimental.current().id)
print("----", "FAIL: %d" % len(fails) if fails else "全部通过")
sys.exit(1 if fails else 0)



