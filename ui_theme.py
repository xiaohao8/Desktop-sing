# -*- coding: utf-8 -*-
"""Theme tokens and theme selection state for Desktop-sing."""
from __future__ import annotations

from dataclasses import dataclass, fields
import winreg

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication


APPEARANCES = ("system", "dark", "light")
RELEASED_THEME_IDS = ("ink", "celadon")
EXPERIMENTAL_THEME_IDS = ("amber",)


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    appearance: str
    bg: str
    surface: str
    surface_raised: str
    surface_sunken: str
    surface_hover: str
    text: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    border: str
    border_strong: str
    divider: str
    accent_fill: str
    accent_text: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    accent_soft: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    focus: str
    selection: str
    shadow: str
    scrollbar_handle: str
    grip_dot: str
    font_display: str
    font_text: str
    font_cjk: str
    fs_display: int
    fs_title: int
    fs_heading: int
    fs_body: int
    fs_small: int
    fs_caption: int
    fs_eyebrow: int
    lh_body: int
    s1: int
    s2: int
    s3: int
    s4: int
    s5: int
    s6: int
    r_control: int
    r_row: int
    r_card: int
    r_window: int
    m_fast: int
    m_base: int
    m_slow: int
    easing: str


def _theme(
    theme_id: str,
    name: str,
    appearance: str,
    bg: str,
    surface: str,
    surface_raised: str,
    surface_sunken: str,
    surface_hover: str,
    text: str,
    text_secondary: str,
    text_muted: str,
    text_disabled: str,
    border: str,
    border_strong: str,
    divider: str,
    accent_fill: str,
    accent_text: str,
    accent_hover: str,
    accent_pressed: str,
    on_accent: str,
    accent_soft: str,
    success: str,
    success_soft: str,
    warning: str,
    warning_soft: str,
    danger: str,
    danger_soft: str,
    focus: str,
    selection: str,
    shadow: str,
    scrollbar_handle: str,
    grip_dot: str,
) -> Theme:
    return Theme(
        id=theme_id,
        name=name,
        appearance=appearance,
        bg=bg,
        surface=surface,
        surface_raised=surface_raised,
        surface_sunken=surface_sunken,
        surface_hover=surface_hover,
        text=text,
        text_secondary=text_secondary,
        text_muted=text_muted,
        text_disabled=text_disabled,
        border=border,
        border_strong=border_strong,
        divider=divider,
        accent_fill=accent_fill,
        accent_text=accent_text,
        accent_hover=accent_hover,
        accent_pressed=accent_pressed,
        on_accent=on_accent,
        accent_soft=accent_soft,
        success=success,
        success_soft=success_soft,
        warning=warning,
        warning_soft=warning_soft,
        danger=danger,
        danger_soft=danger_soft,
        focus=focus,
        selection=selection,
        shadow=shadow,
        scrollbar_handle=scrollbar_handle,
        grip_dot=grip_dot,
        font_display='"Segoe UI Variable Display", "Segoe UI", "MiSans", "Microsoft YaHei UI"',
        font_text='"Segoe UI Variable Text", "Segoe UI", "MiSans", "Microsoft YaHei UI"',
        font_cjk='"MiSans", "Microsoft YaHei UI", sans-serif',
        fs_display=30,
        fs_title=22,
        fs_heading=16,
        fs_body=13,
        fs_small=12,
        fs_caption=12,
        fs_eyebrow=12,
        lh_body=20,
        s1=4,
        s2=8,
        s3=12,
        s4=16,
        s5=24,
        s6=32,
        r_control=8,
        r_row=12,
        r_card=16,
        r_window=22,
        m_fast=120,
        m_base=180,
        m_slow=240,
        easing="cubic-bezier(0.2,0,0,1)",
    )


THEMES: dict[str, dict[str, Theme]] = {
    "ink": {
        "dark": _theme(
            "ink", "墨", "dark",
            "#0B0B0C", "#141416", "#1B1B1E", "#08080A", "#202024",
            "#F3F0E9", "#A8A49B", "#8A867E", "#6E6B65",
            "rgba(255,255,255,.08)", "rgba(255,255,255,.34)", "rgba(255,255,255,.12)",
            "#C94322", "#F06A4A", "#B93C1D", "#A9341A", "#FFF8F0",
            "rgba(201,67,34,.16)", "#63C79A", "rgba(99,199,154,.16)",
            "#E3B15C", "rgba(227,177,92,.16)", "#F06A5E", "rgba(240,106,94,.16)",
            "#F06A4A", "rgba(240,106,74,.24)", "rgba(0,0,0,.42)",
            "rgba(255,255,255,.38)", "rgba(255,255,255,.38)",
        ),
        "light": _theme(
            "ink", "墨", "light",
            "#F2EFE8", "#FAF8F2", "#FFFFFF", "#E9E5DC", "#FFFFFF",
            "#1B1A18", "#4F4B44", "#625D55", "#837E74",
            "rgba(27,26,24,.12)", "rgba(27,26,24,.50)", "rgba(27,26,24,.18)",
            "#C2421F", "#A93618", "#A9341A", "#8F2B16", "#FFF8EF",
            "rgba(194,66,31,.12)", "#176349", "rgba(23,99,73,.14)",
            "#8A5200", "rgba(138,82,0,.14)", "#B3261E", "rgba(179,38,30,.12)",
            "#C2421F", "rgba(194,66,31,.18)", "rgba(27,26,24,.22)",
            "rgba(27,26,24,.50)", "rgba(27,26,24,.50)",
        ),
    },
    "celadon": {
        "dark": _theme(
            "celadon", "青瓷", "dark",
            "#0A1210", "#121B18", "#19251F", "#060C0A", "#1F2C25",
            "#EDF2EC", "#A2B0A7", "#84958B", "#6B7B72",
            "rgba(255,255,255,.09)", "rgba(255,255,255,.34)", "rgba(255,255,255,.13)",
            "#2E9E78", "#5FD0A0", "#35B287", "#2A906E", "#06140F",
            "rgba(46,158,120,.18)", "#63C79A", "rgba(99,199,154,.16)",
            "#D8B36A", "rgba(216,179,106,.16)", "#F08076", "rgba(240,128,118,.16)",
            "#5FD0A0", "rgba(95,208,160,.24)", "rgba(0,0,0,.42)",
            "rgba(255,255,255,.38)", "rgba(255,255,255,.38)",
        ),
        "light": _theme(
            "celadon", "青瓷", "light",
            "#EFF3EE", "#F8FAF6", "#FFFFFF", "#E2E8E1", "#FFFFFF",
            "#14201A", "#46554C", "#55645B", "#707E75",
            "rgba(20,32,26,.13)", "rgba(20,32,26,.52)", "rgba(20,32,26,.20)",
            "#1F7A5A", "#176349", "#1A6A4E", "#155A42", "#F7FFFB",
            "rgba(31,122,90,.13)", "#176349", "rgba(23,99,73,.14)",
            "#7A5200", "rgba(122,82,0,.14)", "#A8342C", "rgba(168,52,44,.12)",
            "#1F7A5A", "rgba(31,122,90,.19)", "rgba(20,32,26,.20)",
            "rgba(20,32,26,.50)", "rgba(20,32,26,.50)",
        ),
    },
    "amber": {
        "dark": _theme(
            "amber", "琥珀", "dark",
            "#0D0C0A", "#171512", "#201D18", "#090806", "#282219",
            "#F2EDE4", "#ADA69A", "#8C8577", "#716A5E",
            "rgba(255,255,255,.09)", "rgba(255,255,255,.34)", "rgba(255,255,255,.13)",
            "#D9912F", "#E8A33D", "#E8A33D", "#C77F22", "#1E1304",
            "rgba(217,145,47,.18)", "#7BC79E", "rgba(123,199,158,.16)",
            "#E8B35C", "rgba(232,179,92,.16)", "#F08076", "rgba(240,128,118,.16)",
            "#E8A33D", "rgba(232,163,61,.24)", "rgba(0,0,0,.42)",
            "rgba(255,255,255,.38)", "rgba(255,255,255,.38)",
        ),
        "light": _theme(
            "amber", "琥珀", "light",
            "#F1EEE6", "#F9F6EF", "#FFFFFF", "#E5E0D6", "#FFFFFF",
            "#1D1A15", "#4F4A41", "#5E584E", "#79736A",
            "rgba(29,26,21,.13)", "rgba(29,26,21,.52)", "rgba(29,26,21,.20)",
            "#9A5B00", "#7D4900", "#7D4900", "#653A00", "#FFF8EC",
            "rgba(154,91,0,.13)", "#176349", "rgba(23,99,73,.14)",
            "#7A5200", "rgba(122,82,0,.14)", "#A8342C", "rgba(168,52,44,.12)",
            "#9A5B00", "rgba(154,91,0,.19)", "rgba(29,26,21,.20)",
            "rgba(29,26,21,.50)", "rgba(29,26,21,.50)",
        ),
    },
}


def system_animations_enabled() -> bool:
    """Whether Windows animations are enabled (Reduce Motion is off)."""
    for module_name in ("winsdk", "winrt"):
        try:
            module = __import__(
                f"{module_name}.windows.ui.viewmanagement",
                fromlist=["UISettings"],
            )
            return bool(module.UISettings().animations_enabled)
        except Exception:
            continue
    return True


class ThemeManager(QObject):
    changed = Signal(object)

    def __init__(
        self,
        theme_id: str = "ink",
        appearance: str = "system",
        parent: QObject | None = None,
        reduce_motion: bool | None = None,
    ) -> None:
        super().__init__(parent)
        if theme_id not in THEMES:
            raise ValueError(f"unknown theme id: {theme_id}")
        if appearance not in APPEARANCES:
            raise ValueError(f"unknown appearance: {appearance}")
        self._theme_id = theme_id
        self._appearance = appearance
        self._reduce_motion = reduce_motion
        self._current = self._resolve()
        self._connect_system_appearance()

    def _connect_system_appearance(self) -> None:
        app = QGuiApplication.instance()
        if app is None:
            return
        try:
            hints = app.styleHints()
            hints.colorSchemeChanged.connect(self._on_system_appearance_changed)
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _on_system_appearance_changed(self, *_args) -> None:
        if self._appearance == "system":
            self._sync()

    def current(self) -> Theme:
        return self._current

    def theme_id(self) -> str:
        return self._theme_id

    def appearance(self) -> str:
        return self._appearance

    def set_theme(self, theme_id: str) -> None:
        if theme_id not in THEMES:
            raise ValueError(f"unknown theme id: {theme_id}")
        if theme_id == self._theme_id:
            return
        self._theme_id = theme_id
        self._sync()

    def set_appearance(self, appearance: str) -> None:
        if appearance not in APPEARANCES:
            raise ValueError(f"unknown appearance: {appearance}")
        if appearance == self._appearance:
            return
        self._appearance = appearance
        self._sync()

    def refresh_system(self) -> Theme:
        self._sync()
        return self._current

    def reduce_motion(self) -> bool:
        if self._reduce_motion is not None:
            return self._reduce_motion
        return not system_animations_enabled()

    def set_reduce_motion(self, enabled: bool | None) -> None:
        if enabled == self._reduce_motion:
            return
        self._reduce_motion = enabled
        self.changed.emit(self._current)

    def duration(self, key: str = "m_base") -> int:
        if self.reduce_motion():
            return 0
        return int(getattr(self._current, key))

    def system_appearance(self) -> str:
        try:
            scheme = QGuiApplication.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
            if scheme == Qt.ColorScheme.Light:
                return "light"
        except (AttributeError, RuntimeError):
            pass

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _value_type = winreg.QueryValueEx(key, "AppsUseLightTheme")
            if value == 0:
                return "dark"
            if value == 1:
                return "light"
        except OSError:
            pass
        return "dark"

    def _resolve(self) -> Theme:
        appearance = (
            self.system_appearance()
            if self._appearance == "system"
            else self._appearance
        )
        return THEMES[self._theme_id][appearance]

    def _sync(self) -> None:
        theme = self._resolve()
        if theme != self._current:
            self._current = theme
            self.changed.emit(theme)


def qss_tokens(theme: Theme) -> dict[str, str]:
    return {field.name: str(getattr(theme, field.name)) for field in fields(theme)}
