# -*- coding: utf-8 -*-
"""Theme tokens and theme selection state for Desktop-sing."""
from __future__ import annotations

from dataclasses import dataclass, fields
import re
from string import Template
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
            "#F3F0E9", "#A8A49B", "#8B877F", "#6E6B65",
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
            "rgba(255,255,255,.09)", "rgba(255,255,255,.36)", "rgba(255,255,255,.13)",
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
               border: 1px solid $border; border-radius: 26px; }
QWidget#body { background: transparent; }
QWidget#titlebar { background: $surface; }
QLabel#pagecrumb { color: $text; font-size: 14px; font-weight: 750; }
QPushButton#quick { background: $surface_raised; color: $text_muted;
                    border: 1px solid $border; border-radius: 13px;
                    padding: 6px 11px; font-size: 12px; font-weight: 650; }
QPushButton#quick:hover { background: $surface_hover; color: $text;
                          border-color: $border_strong; }
QPushButton#quick:pressed { background: $surface_sunken; }
QPushButton#winbtn, QPushButton#winclose { background: transparent; border: none; }
QWidget#sidebar { background: $surface;
                   border-right: 1px solid $divider; }
QLabel#brandmark { background: $accent_fill; color: $on_accent;
                   border-radius: 13px; font-size: 19px; font-weight: 700; }
QLabel#brandname { color: $text; font-size: 17px; font-weight: 800; }
QLabel#brandsub { color: $text_muted; font-size: $fs_captionpx; letter-spacing: 2px; }
QLabel#sidestatus { color: $text_muted; font-size: 12px; padding: 2px 4px; }
QLabel#sidestatus[live="1"] { color: $success; }
QPushButton#nav { text-align: left; padding: 0 11px;
                  border: 2px solid transparent; border-left: 3px solid transparent;
                  border-radius: 10px;
                  color: $text_muted; font-size: 13px; font-weight: 650; }
QPushButton#nav:hover { background: $surface_hover; color: $text; }
QPushButton#nav:pressed { background: $surface_sunken; color: $text; }
QPushButton#nav:checked { background: $surface_raised; color: $text;
                          border-left: 3px solid $accent_fill; }
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
QPushButton#stageghost { background: $surface_raised; color: $text_secondary;
                         border: 1px solid $border; border-radius: 12px;
                         padding: 5px 10px; font-size: 12px; }
QPushButton#stageghost:hover { background: $surface_hover; color: $text; }
QWidget#reportPage, QWidget#historyPage { background: $bg; }
QWidget#reportScroll { background: $bg; border: none; }
QWidget#reportBody { background: transparent; }
QWidget#settingsPage { background: $bg; }
QLabel#reportTitle { color: $text; font-size: 26px; font-weight: 800; }
QLabel#reportSub { color: $text_muted; font-size: 13px; }
QLabel#privacyChip { color: $success; background: $success_soft;
                     border: 1px solid $success; border-radius: 12px;
                     padding: 5px 9px; font-size: 12px; }
QPushButton#dangerGhost { background: transparent; color: $danger;
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
QLabel#reportEmpty { color: $text_muted; background: $surface;
                     border: 1px dashed $border_strong; border-radius: 20px;
                     font-size: 13px; padding: 24px; }
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
QLabel#playlistPageTitle { color: $text; font-size: 26px; font-weight: 800; }
QLabel#playlistSubtitle { color: $text_muted; font-size: 13px; font-weight: 400; }
QFrame#playlistPanel { background: $surface_raised;
                       border: 1px solid $border;
                       border-radius: 16px; }
QLineEdit#playlistInput { background: $surface_sunken; color: $text;
                          border: 1px solid $border;
                          border-radius: 10px; padding: 8px 12px;
                          font-size: 13px; font-weight: 600; }
QLineEdit#playlistInput:hover { border-color: $border_strong; }
QLineEdit#playlistInput:focus { border: 2px solid $focus; }
QLineEdit#playlistInput[error="1"] { border: 2px solid $danger; }
QPushButton#primary { background: $accent_fill; color: $on_accent;
                      border: none; border-radius: 10px;
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
                          border-radius: 12px; text-align: left; }
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
                       border-radius: 16px; }
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
                            border: none; border-radius: 14px; }
QPushButton#historyAction:hover { background: $accent_hover; }
QPushButton#historyAction:focus { border: 2px solid $focus; }
QPushButton#ghost { background: transparent; color: $text;
                    border: 1px solid $border_strong;
                    border-radius: 18px; padding: 6px 16px;
                    font-size: 13px; font-weight: 400; }
QPushButton#ghost:hover { background: $surface_hover; }
QPushButton#nav:focus { border-color: $focus; }
QPushButton#nav:checked:focus { border-color: $focus; }
QPushButton#recent:focus { background: $surface_hover; color: $text;
                           border-left-color: $accent_fill; }
QPushButton#quick:focus, QPushButton#stageghost:focus,
QPushButton#dangerGhost:focus, QPushButton#ghost:focus {
    border: 2px solid $focus; }
QPushButton#historyRow:focus { border-color: $focus; }
QFrame#playbar { background: $surface_raised;
                 border: 1px solid $border; border-radius: 26px; }
QPushButton#playprimary { background: $accent_fill; border: none; border-radius: 23px; }
QPushButton#playprimary:hover { background: $accent_hover; }
QPushButton#playprimary:pressed { background: $accent_pressed; }
QPushButton#playprimary:focus { border: 2px solid $focus; }
QPushButton#playround { background: $surface_hover; border: 1px solid $border;
                        border-radius: 19px; }
QPushButton#playround:hover { background: $surface_sunken; }
QPushButton#playround:pressed { background: $surface_sunken; }
QPushButton#playround:focus { border: 2px solid $focus; }
QLabel#bartitle { color: $text; font-size: 14px; font-weight: 700; }
QLabel#barartist { color: $text_secondary; font-size: 12px; }
QLabel#bartime { color: $text_muted; font-size: 12px;
                 font-feature-settings: "tnum" 1; }
QSlider#progress::groove:horizontal { height: 4px; background: $surface_sunken;
                                      border-radius: 2px; }
QSlider#progress::sub-page:horizontal { background: $accent_fill; border-radius: 2px; }
QSlider#progress::handle:horizontal { width: 12px; height: 12px; margin: -4px 0;
                                     border-radius: 6px;
                                     background: $control_handle_fill;
                                     border: 2px solid $control_handle_outline; }
QSlider#progress::handle:horizontal:hover { width: 12px; height: 12px; margin: -5px 0;
                                            border-radius: 7px;
                                            background: $control_handle_fill;
                                            border: 2px solid $control_handle_outline; }
/* Focus keeps the dual-colour handle but adds an independent high-contrast
   outer ring plus a focus-colour band.  A single $focus border disappears
   into the filled track (1.0-1.76:1), so the outer ring is near-white on
   dark themes and near-black on light themes (>=3:1 against both the
   filled track and the groove/background). */
QSlider#progress::handle:horizontal:focus { width: 18px; height: 18px; margin: -7px 0;
                                            border-radius: 9px;
                                            border: 2px solid $control_handle_focus;
                                            background: qradialgradient(
                                                cx:0.5, cy:0.5, radius:0.5,
                                                fx:0.5, fy:0.5,
                                                stop:0    $control_handle_fill,
                                                stop:0.42 $control_handle_fill,
                                                stop:0.43 $control_handle_outline,
                                                stop:0.60 $control_handle_outline,
                                                stop:0.61 $focus,
                                                stop:0.78 $focus,
                                                stop:0.79 $control_handle_focus,
                                                stop:1    $control_handle_focus); }
QFrame#appearanceCard { background: $surface_raised;
                        border: 1px solid $border;
                        border-radius: 16px; }
QLabel#appearanceTitle { color: $text; font-size: 16px; font-weight: 700; }
QLabel#appearanceHint { color: $text_muted; font-size: 12px; }
QPushButton#appearanceSeg { background: transparent; color: $text_muted;
                            border: 1px solid $border; border-radius: 12px;
                            padding: 7px 14px; font-size: 13px; font-weight: 600; }
QPushButton#appearanceSeg:hover { background: $surface_hover; color: $text; }
QPushButton#appearanceSeg:checked { background: $accent_soft; color: $accent_text;
                                    border-color: $accent_fill; }
QPushButton#appearanceSeg:focus { border: 2px solid $focus; }
QPushButton#themeSwatch { background: $surface; border: 2px solid $border;
                          border-radius: 12px; text-align: left;
                          padding: 10px 12px; }
QLabel#themeSwatchName { color: $text; font-size: 13px; font-weight: 650; }
QLabel#themeSwatchDots { border-radius: 9px; }
QPushButton#themeSwatch:hover { border-color: $border_strong; }
QPushButton#themeSwatch:checked { border: 2px solid $focus; }
QPushButton#themeSwatch:focus { border: 2px solid $focus; }
""")


_OVERLAY_QSS = Template(r"""
* { font-family: $font_text; }
QDialog, QMessageBox, QMenu { background: $surface_raised; color: $text; }
QLabel { color: $text; font-size: $fs_bodypx; background: transparent; }
QLabel#wdtitle { color: $text; font-size: 17px; font-weight: 600; }
QLabel#wdbody { color: $text_secondary; font-size: 13px; }
QPushButton { background: $surface; color: $text;
              border: 1px solid $border; border-radius: $r_controlpx;
              padding: 6px 18px; min-width: 60px; }
QPushButton:hover { border-color: $focus; }
QPushButton:default { background: $accent_fill; color: $on_accent;
                      border: none; font-weight: 700; }
QPushButton:default:hover { background: $accent_hover; }
QPushButton#wdgo { background: $accent_fill; color: $on_accent; border: none;
                   border-radius: $r_controlpx; padding: 8px 18px; font-weight: 600; }
QPushButton#wdgo:hover { background: $accent_hover; }
QPushButton#wdghost { background: transparent; color: $text_muted;
                      border: 1px solid $border_strong;
                      border-radius: $r_controlpx; padding: 8px 16px; }
QPushButton#wdghost:hover { color: $text; border-color: $focus; }
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
