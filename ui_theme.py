# -*- coding: utf-8 -*-
"""Theme tokens and theme selection state for Desktop-sing."""
from __future__ import annotations

from dataclasses import dataclass, fields
import re
from string import Template
import winreg

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication


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
    control_handle_fill: str
    control_handle_outline: str
    control_handle_focus: str
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
    glass_fill: str = "rgba(255,255,255,.07)"
    glass_border: str = "rgba(255,255,255,.18)"
    glass_hover: str = "rgba(255,255,255,.13)"
    glass_highlight: str = "rgba(255,255,255,.30)"
    glass_shadow: str = "rgba(0,0,0,.32)"


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
    control_handle_fill: str | None = None,
    control_handle_outline: str | None = None,
    control_handle_focus: str | None = None,
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
        control_handle_fill=control_handle_fill or on_accent,
        control_handle_outline=control_handle_outline or text,
        control_handle_focus=(
            control_handle_focus
            or ("#FFFFFF" if appearance == "dark" else "#000000")
        ),
        glass_fill=("rgba(255,255,255,.07)" if appearance == "dark"
                    else "rgba(255,255,255,.72)"),
        glass_border=("rgba(255,255,255,.20)" if appearance == "dark"
                      else "rgba(20,20,24,.12)"),
        glass_hover=("rgba(255,255,255,.13)" if appearance == "dark"
                     else "rgba(255,255,255,.92)"),
        glass_highlight=("rgba(255,255,255,.34)" if appearance == "dark"
                         else "rgba(255,255,255,.95)"),
        glass_shadow=("rgba(0,0,0,.42)" if appearance == "dark"
                      else "rgba(20,20,24,.22)"),
        font_display='"Segoe UI Variable Display", "Segoe UI", "MiSans", "Microsoft YaHei UI"',
        font_text='"Segoe UI Variable Text", "Segoe UI", "MiSans", "Microsoft YaHei UI"',
        font_cjk='"MiSans", "Microsoft YaHei UI", sans-serif',
        fs_display=34,
        fs_title=22,
        fs_heading=17,
        fs_body=14,
        fs_small=13,
        fs_caption=12,
        fs_eyebrow=12,
        lh_body=21,
        s1=4,
        s2=8,
        s3=12,
        s4=18,
        s5=24,
        s6=32,
        r_control=12,
        r_row=14,
        r_card=20,
        r_window=26,
        m_fast=120,
        m_base=180,
        m_slow=240,
        easing="cubic-bezier(0.2,0,0,1)",
    )


THEMES: dict[str, dict[str, Theme]] = {
    "ink": {
        "dark": _theme(
            "ink", "墨", "dark",
            "#000000", "#1C1C1E", "#1C1C1E", "#0D0D0F", "#2C2C2E",
            "#F3F0E9", "#B0ADA5", "#A6A6AB", "#8A8A8F",
            "rgba(255,255,255,.08)", "rgba(255,255,255,.36)", "rgba(255,255,255,.12)",
            "#C94322", "#F06A4A", "#B93C1D", "#A9341A", "#FFF8F0",
            "rgba(201,67,34,.16)", "#63C79A", "rgba(99,199,154,.16)",
            "#E3B15C", "rgba(227,177,92,.16)", "#F06A5E", "rgba(240,106,94,.16)",
            "#F06A4A", "rgba(240,106,74,.24)", "rgba(0,0,0,.42)",
            "rgba(255,255,255,.38)", "rgba(255,255,255,.38)",
            None, "#0B0B0C",
        ),
        "light": _theme(
            "ink", "墨", "light",
            "#F2F2F7", "#FFFFFF", "#FFFFFF", "#E5E5EA", "#EFEFF4",
            "#1B1A18", "#4F4B44", "#625D55", "#837E74",
            "rgba(60,60,67,.10)", "rgba(60,60,67,.64)", "rgba(60,60,67,.12)",
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
            "#000000", "#1A2620", "#1A2620", "#0C1712", "#243029",
            "#EDF2EC", "#B4C2B8", "#ADBCB2", "#93A79B",
            "rgba(255,255,255,.09)", "rgba(255,255,255,.36)", "rgba(255,255,255,.13)",
            "#2E9E78", "#5FD0A0", "#35B287", "#2A906E", "#06140F",
            "rgba(46,158,120,.18)", "#63C79A", "rgba(99,199,154,.16)",
            "#D8B36A", "rgba(216,179,106,.16)", "#F08076", "rgba(240,128,118,.16)",
            "#5FD0A0", "rgba(95,208,160,.24)", "rgba(0,0,0,.42)",
            "rgba(255,255,255,.38)", "rgba(255,255,255,.38)",
        ),
        "light": _theme(
            "celadon", "青瓷", "light",
            "#F2F7F3", "#FFFFFF", "#FFFFFF", "#E4EDE7", "#EDF3EF",
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
            "#F2EDE4", "#ADA69A", "#90897B", "#736C60",
            "rgba(255,255,255,.09)", "rgba(255,255,255,.36)", "rgba(255,255,255,.13)",
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
        allow_experimental: bool = False,
    ) -> None:
        super().__init__(parent)
        self._allow_experimental = allow_experimental
        self._validate_theme_id(theme_id)
        if appearance not in APPEARANCES:
            raise ValueError(f"unknown appearance: {appearance}")
        self._theme_id = theme_id
        self._appearance = appearance
        self._reduce_motion = reduce_motion
        self._current = self._resolve()
        self._connect_system_appearance()

    def _validate_theme_id(self, theme_id: str) -> None:
        if theme_id not in THEMES:
            raise ValueError(f"unknown theme id: {theme_id}")
        if theme_id in EXPERIMENTAL_THEME_IDS and not self._allow_experimental:
            raise ValueError(f"experimental theme is not user selectable: {theme_id}")

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
        self._validate_theme_id(theme_id)
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


# ---------------------------------------------------------------------------
# QSS builders
#
# Templates use ``string.Template`` ``$token`` placeholders: QSS is full of
# ``{}`` braces which would fight ``str.format``. Every colour that styles
# application chrome (window shell, bars, menus, dialogs) is emitted here and
# only here, so the widget code stays free of colour literals.

_MAIN_QSS = Template(r"""
* { font-family: $font_text; }
QFrame#shell { background: $bg;
               border: 1px solid $border; border-radius: 28px; }
QWidget#body { background: transparent; }
QWidget#titlebar { background: $bg; }
QLabel#pagecrumb { color: $text; font-size: 14px; font-weight: 750; }
QPushButton#quick { background: $glass_fill; color: $text_muted;
                    border: 1px solid $glass_border; border-radius: 12px;
                    padding: 6px 11px; font-size: 12px; font-weight: 650; }
QPushButton#quick:hover { background: $glass_hover; color: $text;
                          border-color: $glass_highlight; }
QPushButton#quick:pressed { background: $glass_fill; }
QPushButton#winbtn, QPushButton#winclose { background: transparent; border: none; }
QWidget#sidebar { background: $bg;
                   border-right: 1px solid $divider; }
QLabel#brandmark { background: $accent_fill; color: $on_accent;
                   border-radius: 13px; font-size: 19px; font-weight: 700; }
QLabel#brandname { color: $text; font-size: 17px; font-weight: 800; }
QLabel#brandsub { color: $text_muted; font-size: $fs_captionpx; letter-spacing: 2px; }
QLabel#sidestatus { color: $text_muted; font-size: 12px; padding: 2px 4px; }
QLabel#sidestatus[live="1"] { color: $success; }QPushButton#nav { text-align: left; padding: 0 11px;
                  border: 2px solid transparent; border-left: 3px solid transparent;
                  border-radius: 10px;
                  color: $text_muted; font-size: 13px; font-weight: 650; }
QPushButton#nav:hover { background: $glass_hover; color: $text;
                        border-color: $glass_border; border-left-color: $accent_fill; }
QPushButton#nav:pressed { background: $glass_fill; color: $text; }
QPushButton#nav:checked { background: $accent_soft; color: $text;
                          border-left: 3px solid transparent; }
QLabel#sidehead { color: $text_muted; font-size: $fs_eyebrowpx; font-weight: 700;
                  letter-spacing: 1px; }
QLabel#sidecount { color: $text_muted; font-size: $fs_smallpx; }
QLabel#sideempty { color: $text_disabled; font-size: 12px; padding: 8px 4px; }
QPushButton#recent { background: transparent; color: $text_secondary; border: none;
                     border-left: 3px solid transparent; border-radius: 11px;
                     padding: 7px 9px 7px 11px; text-align: left;
                     font-size: 12px; }
QPushButton#recent:hover { background: $surface_hover; color: $text;
                           border-left-color: $accent_fill; }
QLabel#sidetip { color: $text_muted; font-size: $fs_smallpx;
                 border-top: 1px solid $divider; padding-top: 10px; }
QStackedWidget#stack { background: transparent; }
QWidget#stage { background: $bg; }
QLabel#stageeyebrow { color: $text_muted; font-size: $fs_eyebrowpx;
                      letter-spacing: 2px; font-weight: 700; }
QLabel#stagetrack { color: $text; font-size: 26px; font-weight: 800; }
QLabel#stageartist { color: $text_secondary; font-size: 13px; }
QPushButton#stageghost { background: $glass_fill; color: $text_secondary;
                         border: 1px solid $glass_border; border-radius: 12px;
                         padding: 5px 10px; font-size: 12px; }
QPushButton#stageghost:hover { background: $glass_hover; color: $text;
                              border-color: $glass_highlight; }
QWidget#reportPage, QWidget#historyPage { background: $bg; }
QWidget#reportScroll { background: $bg; border: none; }
QWidget#reportBody { background: transparent; }
QWidget#settingsPage { background: $bg; }
QLabel#reportTitle { color: $text; font-size: 26px; font-weight: 800; }
QLabel#reportSub { color: $text_muted; font-size: 13px; }
QPushButton#dangerGhost { background: $glass_fill; color: $danger;
                          border: 1px solid $danger; border-radius: 12px;
                          padding: 6px 10px; font-size: 12px; }
QPushButton#dangerGhost:hover { background: $danger; color: $bg; }
QFrame#reportHero { background: $surface_raised;
                    border: 1px solid $border; border-top-color: $border_strong;
                    border-radius: 24px; }
QLabel#heroCaption { color: $text_muted; font-size: 12px; font-weight: 700; }
QLabel#heroChip { color: $accent_text; background: $accent_soft;
                  border-radius: 10px; padding: 4px 9px; font-size: $fs_smallpx; }
QLabel#heroValue { color: $text; font-size: 56px; font-weight: 700; }
QLabel#heroUnit { color: $text_muted; font-size: 12px; }
QFrame#statTile, QFrame#reportCard {
    background: $surface_raised;
    border: 1px solid $border; border-top-color: $border_strong;
    border-radius: 16px; }
QLabel#statValue { color: $text; font-size: 27px; font-weight: 700; }
QLabel#statCaption { color: $text_muted; font-size: $fs_smallpx; }
QLabel#cardHead { color: $text_muted; font-size: $fs_eyebrowpx; font-weight: 700;
                  letter-spacing: 1px; }
QLabel#artistBig { color: $text; font-size: 24px; font-weight: 800; }
QLabel#artistMeta { color: $accent_text; font-size: 12px; font-weight: 700;
                    font-feature-settings: "tnum" 1; }
QLabel#muted { color: $text_muted; font-size: 12px; }
QLabel#rankList, QLabel#trackRank { color: $text_secondary; font-size: 12px; }
QFrame#reportEmptyCard { background: $surface_raised;
                         border: 1px solid $border; border-top-color: $border_strong;
                         border-radius: 24px; }
QLabel#reportEmptyTitle { color: $text; font-size: 22px; font-weight: 800; }
QLabel#reportEmptyHint { color: $text_muted; font-size: 13px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: $scrollbar_handle; border-radius: 4px;
                              min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $border_strong; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel#historyPageTitle { color: $text; font-size: 28px; font-weight: 600; }
QLabel#historyPageSub { color: $text_muted; font-size: 20px; font-weight: 400; }
QWidget#historyRow { background: transparent; border: none;
                     border-bottom: 1px solid $divider; border-radius: 12px; }
QWidget#historyRow:hover { background: $surface_hover; }
QWidget#historyRow[current="1"] { background: $accent_soft;
                                  border-left: 3px solid $accent_fill; }
QWidget#historyRow[external="1"] { background: transparent;
                                   border-left: 3px solid transparent; }
QWidget#historyRow[external="1"] QLabel { color: $text_disabled; }
QLabel#historyCover { background: $surface_raised; color: $text_secondary;
                      border-radius: 8px; font-size: 18px; font-weight: 600; }
QLabel#historyTitle { color: $text; font-size: 15px; font-weight: 600; }
QLabel#historyArtist { color: $text_muted; font-size: 12px; font-weight: 400; }
QLabel#historyMeta { color: $text_muted; font-size: 12px; font-weight: 400;
                     font-feature-settings: "tnum" 1; }
QWidget#playlistPage { background: $bg; }
QLabel#playlistPageTitle { color: $text; font-size: 32px; font-weight: 800; }
QLabel#playlistSubtitle { color: $text_muted; font-size: 13px; font-weight: 400; }
QFrame#playlistPanel { background: $surface_raised;
                       border: 1px solid $border;
                       border-radius: 20px; }
QLineEdit#playlistInput { background: $surface_sunken; color: $text;
                          border: none;
                          border-radius: 12px; padding: 10px 14px;
                          font-size: 13px; font-weight: 600; }
QLineEdit#playlistInput:hover { border-color: $border_strong; }
QLineEdit#playlistInput:focus { border: 2px solid $focus; }
QLineEdit#playlistInput[error="1"] { border: 2px solid $danger; }
QPushButton#primary { background: $accent_fill; color: $on_accent;
                      border: 1px solid $glass_highlight; border-radius: 10px;
                      padding: 8px 16px; font-size: 13px; font-weight: 600; }
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:pressed { background: $accent_pressed; }
QPushButton#primary:focus { border: 2px solid $focus; }
QPushButton#primary:disabled { background: $surface_sunken; color: $text_disabled; }
QLabel#playlistCompliance { color: $text_muted; font-size: 12px; font-weight: 400; }
QLabel#playlistError { color: $danger; font-size: 12px; font-weight: 400; }
QLabel#playlistSuccess { color: $success; font-size: 12px; font-weight: 500; }
QLabel#playlistSection { color: $text; font-size: 16px; font-weight: 700; }
QLabel#playlistCount { color: $text_muted; font-size: 12px; font-weight: 500; }
QPushButton#playlistRow { background: transparent;
                          border: none;
                          border-bottom: 1px solid $divider;
                          border-radius: 14px; text-align: left; }
QPushButton#playlistRow:hover { background: $surface_hover; }
QPushButton#playlistRow:pressed { background: $accent_soft; }
QPushButton#playlistRow:checked { background: $accent_soft;
                                  border-left: 3px solid $accent_fill; }
QPushButton#playlistRow:focus { border: 2px solid $focus; }
QLabel#playlistCover { background: $surface_raised; color: $text_secondary;
                       border-radius: 8px; font-size: 18px; font-weight: 600; }
QLabel#playlistTitle { color: $text; font-size: 14px; font-weight: 600; }
QLabel#playlistArtist { color: $text_secondary; font-size: 12px; font-weight: 400; }
QLabel#playlistMeta { color: $text_muted; font-size: 12px; font-weight: 400;
                      font-feature-settings: "tnum" 1; }
QLabel#playlistStatus { color: $text_muted; font-size: 12px; font-weight: 500; }
QLabel#playlistStatus[matched="1"] { color: $success; }
QFrame#playlistSkeleton { background: $surface;
                          border-bottom: 1px solid $divider; }
QLabel#playlistSkeletonCover { background: $surface_raised; border-radius: 8px; }
QLabel#playlistSkeletonLine { background: $surface_raised; border-radius: 6px; }
QFrame#playlistEmpty { background: $surface_raised;
                       border: 1px solid $border;
                       border-radius: 20px; }
QLabel#playlistEmptyIcon { color: $text_muted; font-size: 48px; font-weight: 400; }
QLabel#playlistEmptyTitle { color: $text; font-size: 20px; font-weight: 600; }
QLabel#playlistEmptyDesc { color: $text_muted; font-size: 13px; font-weight: 400; }
QLabel#historyEmptyIcon { color: $text_muted; font-size: 48px; font-weight: 400; }
QLabel#historyEmptyTitle { color: $text; font-size: 20px; font-weight: 600; }
QLabel#historyEmptyDesc { color: $text_muted; font-size: 13px; font-weight: 400; }
QFrame#historySkeleton { background: $surface;
                         border-bottom: 1px solid $divider; }
QLabel#historySkeletonCover { background: $surface_raised; border-radius: 8px; }
QLabel#historySkeletonLine { background: $surface_raised; border-radius: 6px; }
QPushButton#historyAction { background: $accent_fill; color: $on_accent;
                            border: 1px solid $glass_highlight;
                            border-radius: 14px; }
QPushButton#historyAction:hover { background: $accent_hover; }
QPushButton#historyAction:focus { border: 2px solid $focus; }
QPushButton#ghost { background: $glass_fill; color: $text;
                    border: 1px solid $glass_border;
                    border-radius: 18px; padding: 6px 16px;
                    font-size: 13px; font-weight: 400; }
QPushButton#ghost:hover { background: $glass_hover;
                          border-color: $glass_highlight; }
QPushButton#nav:focus { border-color: $focus; }
QPushButton#nav:checked:focus { border-color: $focus; }
QPushButton#recent:focus { background: $surface_hover; color: $text;
                           border-left-color: $accent_fill; }
QPushButton#quick:focus, QPushButton#stageghost:focus,
QPushButton#dangerGhost:focus, QPushButton#ghost:focus {
    border: 2px solid $focus; }
QPushButton#historyRow:focus { border-color: $focus; }
QFrame#playbar { background: $surface_raised;
                 border: none; border-radius: 24px; }
QPushButton#playprimary { background: $accent_fill; border: 1px solid $glass_highlight;
                         border-radius: 23px; }
QPushButton#playprimary:hover { background: $accent_hover; }
QPushButton#playprimary:pressed { background: $accent_pressed; }
QPushButton#playprimary:focus { border: 2px solid $focus; }
QPushButton#playround { background: $glass_fill; border: 1px solid $glass_border;
                        border-radius: 19px; }
QPushButton#playround:hover { background: $glass_hover;
                              border-color: $glass_highlight; }
QPushButton#playround:pressed { background: $glass_fill; }
QPushButton#playround:focus { border: 2px solid $focus; }
QLabel#bartitle { color: $text; font-size: 14px; font-weight: 700; }
QLabel#barartist { color: $text_secondary; font-size: 12px; }
QLabel#bartime { color: $text_muted; font-size: 12px;
                 font-feature-settings: "tnum" 1; }
QSlider#progress::groove:horizontal { height: 3px; background: $surface_sunken;
                                      border-radius: 2px; }
QSlider#progress::sub-page:horizontal { background: $accent_fill; border-radius: 2px; }
QSlider#progress::handle:horizontal { width: 5px; height: 15px; margin: -6px 0;
                                     border-radius: 3px;
                                     background: $text; }
QSlider#progress::handle:horizontal:hover { width: 7px; height: 17px; margin: -7px 0;
                                            border-radius: 4px;
                                            background: $text; }
QSlider#progress::handle:horizontal:focus { width: 7px; height: 17px; margin: -7px 0;
                                            border-radius: 4px;
                                            border: 2px solid $control_handle_focus;
                                            background: $text; }
QFrame#appearanceCard { background: $surface_raised;
                        border: 1px solid $border;
                        border-radius: 20px; }
QLabel#appearanceTitle { color: $text; font-size: 17px; font-weight: 800; }
QFrame#sectionBar { background: $accent_fill; border-radius: 1.5px; }
QLabel#appearanceHint { color: $text_muted; font-size: 12px; }
QWidget#divider { background: $divider; max-height: 1px; }
QPushButton#appearanceSeg { background: $glass_fill; color: $text_muted;
                            border: 1px solid $glass_border; border-radius: 12px;
                            padding: 7px 14px; font-size: 13px; font-weight: 600; }
QPushButton#appearanceSeg:hover { background: $glass_hover; color: $text;
                                  border-color: $glass_highlight; }
QPushButton#appearanceSeg:checked { background: $accent_soft; color: $accent_text;
                                    border-color: $accent_fill; }
QPushButton#appearanceSeg:focus { border: 2px solid $focus; }
QPushButton#themeSwatch { background: $surface; border: 1px solid $border;
                          border-radius: 16px; text-align: left;
                          min-height: 96px; padding: 12px 14px; }
QLabel#themeSwatchName { color: $text; font-size: 13px; font-weight: 650; }
QLabel#themeSwatchCheck { color: $text; font-size: 13px; font-weight: 700; }
QPushButton#themeSwatch:hover { border-color: $border_strong; }
QPushButton#themeSwatch:checked { border: 2px solid $border_strong;
                                  background: $surface_raised; }
QPushButton#themeSwatch:focus { border: 2px solid $focus; }
""")


_OVERLAY_QSS = Template(r"""
* { font-family: $font_text; }
QDialog, QMessageBox, QMenu { background: $surface_raised; color: $text; }
QLabel { color: $text; font-size: $fs_bodypx; background: transparent; }
QLabel#wdtitle { color: $text; font-size: 17px; font-weight: 600; }
QLabel#wdbody { color: $text_secondary; font-size: 13px; }
QPushButton { background: $glass_fill; color: $text;
              border: 1px solid $glass_border; border-radius: $r_controlpx;
              padding: 6px 18px; min-width: 60px; }
QPushButton:hover { background: $glass_hover; border-color: $glass_highlight; }
QPushButton:default { background: $accent_fill; color: $on_accent;
                      border: 1px solid $glass_highlight; font-weight: 700; }
QPushButton:default:hover { background: $accent_hover; }
QPushButton#wdgo { background: $accent_fill; color: $on_accent;
                   border: 1px solid $glass_highlight;
                   border-radius: $r_controlpx; padding: 8px 18px; font-weight: 600; }
QPushButton#wdgo:hover { background: $accent_hover; }
QPushButton#wdghost { background: $glass_fill; color: $text_muted;
                      border: 1px solid $glass_border;
                      border-radius: $r_controlpx; padding: 8px 16px; }
QPushButton#wdghost:hover { color: $text; border-color: $glass_highlight; }
QPushButton:focus { border: 2px solid $focus; }
QPushButton:hover:focus { border-color: $focus; }
QPushButton:default:focus { border: 2px solid $focus; }
QPushButton#wdgo:focus { border: 2px solid $focus; }
QPushButton#wdghost:focus { border: 2px solid $focus; }
QPushButton:disabled:focus { border-color: $border; }
QMessageBox QLabel { color: $text; font-size: $fs_bodypx; }
QMessageBox QLabel#qt_msgbox_informativelabel { color: $text_muted;
                                                font-size: $fs_captionpx; }
QMenu { background: $surface_raised; color: $text;
        font-size: $fs_bodypx;
        border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 30px 7px 26px; border-radius: 7px; }
QMenu::item:selected { background: $accent_fill; color: $on_accent; }
QMenu::item:disabled { color: $text_disabled; }
QMenu::separator { height: 1px; background: $divider; margin: 6px 10px; }
QMenu::indicator { width: 14px; height: 14px; margin-left: 7px; }
QMenu::indicator:checked { background: $accent_fill; border-radius: 4px; }
QMenu::right-arrow { width: 12px; }
QToolTip { background: $surface_raised; color: $text;
           border: 1px solid $border; padding: 4px 6px; }
QWidget#overlaySurface { background: $surface_raised; color: $text; }
QWidget#overlaySunken { background: $surface_sunken; color: $text; }
""")


_PLACEHOLDER_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


# ---- contrast helpers ---------------------------------------------------
# 浅色外观最容易出问题的是「把深色写死的透明度/颜色原样继承」：白底上的
# 46/255 墨色只有 1.5:1，等于隐形。这些函数把「可读」变成可计算、可断言
# 的量，界面与冒烟测试共用同一套判据。

_NEAR_BLACK = (24, 24, 24)


def rgb_of(color) -> tuple[int, int, int]:
    """RGB tuple for ``#RRGGBB`` / QColor. Alpha-bearing tokens are rejected."""
    if isinstance(color, QColor):
        return color.red(), color.green(), color.blue()
    text = str(color).strip()
    if len(text) == 7 and text.startswith("#"):
        return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
    raise ValueError("expected #RRGGBB or QColor, got %r" % (color,))


def luminance(color) -> float:
    """WCAG 2.x relative luminance (0 = black, 1 = white)."""
    def channel(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb_of(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg, bg) -> float:
    """WCAG contrast ratio, 1.0 (identical) … 21.0 (black on white)."""
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, bg, alpha: float) -> QColor:
    """Composite ``fg`` over ``bg`` at ``alpha`` (0…1), returning an opaque colour."""
    fr, fg_, fb = rgb_of(fg)
    br, bg_, bb = rgb_of(bg)
    a = max(0.0, min(1.0, float(alpha)))
    return QColor(int(round(fr * a + br * (1 - a))),
                  int(round(fg_ * a + bg_ * (1 - a))),
                  int(round(fb * a + bb * (1 - a))))


def readable_on(fg, bg, target: float = 4.5) -> QColor:
    """Darken ``fg`` towards near-black until it reaches ``target`` on ``bg``.

    Used for cover-derived accents on the light stage: a pastel cover colour
    can sit at 2.6:1 on a pale wash, which makes the karaoke line unreadable.
    Dark themes skip this because a bright accent on black is already legible.
    """
    r, g, b = rgb_of(fg)
    for step in range(0, 71):
        t = step / 100.0
        candidate = QColor(int(round(r * (1 - t) + _NEAR_BLACK[0] * t)),
                           int(round(g * (1 - t) + _NEAR_BLACK[1] * t)),
                           int(round(b * (1 - t) + _NEAR_BLACK[2] * t)))
        if contrast_ratio(candidate, bg) >= target:
            return candidate
    return QColor(*_NEAR_BLACK)


def build_qss(theme: Theme, scope: str = "main") -> str:
    """Render the application-chrome stylesheet for ``theme``.

    ``scope="main"`` covers the player window (shell/titlebar/sidebar/now/
    report/history/playlist/settings). ``scope="overlay"`` covers floating
    chrome (menus, message boxes, the welcome dialog, tray surfaces) which are
    top-level widgets and therefore do not inherit a parent stylesheet.

    The result is guaranteed to contain no unresolved ``$token`` placeholder.
    """
    if scope == "main":
        template = _MAIN_QSS
    elif scope == "overlay":
        template = _OVERLAY_QSS
    else:
        raise ValueError(f"unknown qss scope: {scope}")
    tokens = qss_tokens(theme)
    tokens["fs_bodypx"] = "%spx" % tokens["fs_body"]
    tokens["fs_captionpx"] = "%spx" % tokens["fs_caption"]
    tokens["fs_smallpx"] = "%spx" % tokens["fs_small"]
    tokens["fs_eyebrowpx"] = "%spx" % tokens["fs_eyebrow"]
    tokens["r_controlpx"] = "%spx" % tokens["r_control"]
    tokens["r_rowpx"] = "%spx" % tokens["r_row"]
    tokens["r_cardpx"] = "%spx" % tokens["r_card"]
    rendered = template.substitute(tokens)
    leftover = _PLACEHOLDER_RE.findall(rendered)
    if leftover:
        raise ValueError("unresolved qss placeholders: %s" % sorted(set(leftover)))
    return rendered
