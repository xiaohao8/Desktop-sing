# -*- coding: utf-8 -*-
"""Main player window for Desktop-sing.

The desktop lyric bar stays available as mini mode. This module owns the larger
player experience: library navigation, a full lyric stage, local listening
history and the on-device report.
"""
from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsDropShadowEffect,
    QScrollArea, QSizeGrip, QSizePolicy, QSlider, QSpacerItem,
    QStackedWidget, QVBoxLayout,
    QWidget,
)


INK = "#1c2026"
INK_SOFT = "#6e716f"
PAPER = "#faf8f3"
PAPER_DEEP = "#f2ede4"
VERMILION = "#f0643a"
STAGE = "#080a0f"
STAGE_SOFT = "#151820"
LINE = "rgba(24,28,34,18)"

_UI_FONT_FAMILY_CACHE = None


def _ui_font_family() -> str:
    global _UI_FONT_FAMILY_CACHE
    if _UI_FONT_FAMILY_CACHE:
        return _UI_FONT_FAMILY_CACHE
    try:
        from PySide6.QtGui import QFontDatabase
        fams = set(QFontDatabase.families())
        for name in ("Microsoft YaHei UI", "Microsoft YaHei", "MiSans", "Segoe UI"):
            if name in fams:
                _UI_FONT_FAMILY_CACHE = name
                return name
    except Exception:
        pass
    try:
        _UI_FONT_FAMILY_CACHE = QApplication.font().family()
    except Exception:
        _UI_FONT_FAMILY_CACHE = "Microsoft YaHei UI"
    return _UI_FONT_FAMILY_CACHE


def reset_ui_font_cache():
    """Invalidate the font choice after bundled/downloaded fonts are loaded."""
    global _UI_FONT_FAMILY_CACHE
    _UI_FONT_FAMILY_CACHE = None


def _identity(s: str) -> str:
    return s


class IconButton(QPushButton):
    """Button that gets a soft lift on hover without shifting its layout."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._shadow = None

    def enterEvent(self, e):
        if self._shadow is None:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(22)
            shadow.setOffset(0, 7)
            shadow.setColor(QColor(0, 0, 0, 130))
            self.setGraphicsEffect(shadow)
            self._shadow = shadow
        super().enterEvent(e)


def _pick_ui_font(px: int, bold: bool = False, serif: bool = False) -> QFont:
    family = _ui_font_family()
    if serif:
        try:
            from PySide6.QtGui import QFontDatabase
            if "Georgia" in QFontDatabase.families():
                family = "Georgia"
        except Exception:
            pass
    f = QFont(family)
    # The offscreen Windows platform has no font database by default. Setting an
    # explicit family there would render every glyph as a box; fall back to the
    # application font when no family is actually available.
    try:
        from PySide6.QtGui import QFontDatabase
        if family not in QFontDatabase.families():
            f = QFont(QApplication.font())
    except Exception:
        pass
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _format_duration(seconds: float, tr) -> str:
    """Human-friendly duration for rows and cards.

    A 20-second preview must not render as “0 分钟” in history: that looks like
    a broken counter. Show seconds below one minute, whole minutes above it.
    """
    sec = max(0.0, float(seconds or 0.0))
    if sec < 60.0:
        return "%d %s" % (int(round(sec)), tr("秒"))
    return "%d %s" % (int(round(sec / 60.0)), tr("分钟"))


def _draw_icon(p: QPainter, kind: str, r: QRectF, color: QColor):
    """Small line icons drawn with primitives, so no icon font is required."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(color, max(1.4, r.width() * 0.085),
                  Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    if kind == "play":
        path = QPainterPath()
        path.moveTo(x + w * 0.34, y + h * 0.20)
        path.lineTo(x + w * 0.78, y + h * 0.50)
        path.lineTo(x + w * 0.34, y + h * 0.80)
        path.closeSubpath()
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    elif kind == "pause":
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(x + w * 0.30, y + h * 0.22, w * 0.12, h * 0.56), 1.5, 1.5)
        p.drawRoundedRect(QRectF(x + w * 0.58, y + h * 0.22, w * 0.12, h * 0.56), 1.5, 1.5)
    elif kind == "prev":
        p.drawLine(QPoint(int(x + w * 0.28), int(y + h * 0.22)),
                   QPoint(int(x + w * 0.28), int(y + h * 0.78)))
        path = QPainterPath()
        path.moveTo(x + w * 0.72, y + h * 0.22)
        path.lineTo(x + w * 0.38, y + h * 0.50)
        path.lineTo(x + w * 0.72, y + h * 0.78)
        path.closeSubpath()
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    elif kind == "next":
        p.drawLine(QPoint(int(x + w * 0.72), int(y + h * 0.22)),
                   QPoint(int(x + w * 0.72), int(y + h * 0.78)))
        path = QPainterPath()
        path.moveTo(x + w * 0.28, y + h * 0.22)
        path.lineTo(x + w * 0.62, y + h * 0.50)
        path.lineTo(x + w * 0.28, y + h * 0.78)
        path.closeSubpath()
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawPath(path)
    elif kind == "report":
        p.drawLine(QPoint(int(x + w * 0.20), int(y + h * 0.78)),
                   QPoint(int(x + w * 0.20), int(y + h * 0.48)))
        p.drawLine(QPoint(int(x + w * 0.44), int(y + h * 0.78)),
                   QPoint(int(x + w * 0.44), int(y + h * 0.24)))
        p.drawLine(QPoint(int(x + w * 0.68), int(y + h * 0.78)),
                   QPoint(int(x + w * 0.68), int(y + h * 0.40)))
        p.drawLine(QPoint(int(x + w * 0.14), int(y + h * 0.84)),
                   QPoint(int(x + w * 0.80), int(y + h * 0.84)))
    elif kind == "history":
        p.drawEllipse(QRectF(x + w * 0.18, y + h * 0.18, w * 0.64, h * 0.64))
        p.drawLine(QPoint(int(x + w * 0.50), int(y + h * 0.32)),
                   QPoint(int(x + w * 0.50), int(y + h * 0.52)))
        p.drawLine(QPoint(int(x + w * 0.50), int(y + h * 0.52)),
                   QPoint(int(x + w * 0.65), int(y + h * 0.62)))
    elif kind == "settings":
        p.drawEllipse(QRectF(x + w * 0.33, y + h * 0.33, w * 0.34, h * 0.34))
        for i in range(6):
            a = i * math.pi / 3.0
            p.drawLine(QPoint(int(x + w * 0.50 + math.cos(a) * w * 0.30),
                              int(y + h * 0.50 + math.sin(a) * h * 0.30)),
                       QPoint(int(x + w * 0.50 + math.cos(a) * w * 0.42),
                              int(y + h * 0.50 + math.sin(a) * h * 0.42)))
    elif kind == "mini":
        p.drawRoundedRect(QRectF(x + w * 0.16, y + h * 0.28, w * 0.68, h * 0.44), 3, 3)
        p.drawLine(QPoint(int(x + w * 0.50), int(y + h * 0.82)),
                   QPoint(int(x + w * 0.50), int(y + h * 0.94)))
    elif kind == "expand":
        for sx, sy, dx, dy in ((0.18, 0.18, 0.42, 0.42),
                               (0.82, 0.18, 0.58, 0.42),
                               (0.18, 0.82, 0.42, 0.58),
                               (0.82, 0.82, 0.58, 0.58)):
            p.drawLine(QPoint(int(x + w * sx), int(y + h * sy)),
                       QPoint(int(x + w * dx), int(y + h * dy)))
    elif kind == "note":
        p.drawLine(QPoint(int(x + w * 0.40), int(y + h * 0.28)),
                   QPoint(int(x + w * 0.40), int(y + h * 0.70)))
        p.drawLine(QPoint(int(x + w * 0.40), int(y + h * 0.28)),
                   QPoint(int(x + w * 0.76), int(y + h * 0.22)))
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(x + w * 0.20, y + h * 0.62, w * 0.26, h * 0.18))
    p.restore()


def _icon(kind: str, color: str = INK, size: int = 18) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    _draw_icon(p, kind, QRectF(1, 1, size * 2 - 2, size * 2 - 2), QColor(color))
    p.end()
    return QIcon(pm)


class NavButton(QPushButton):
    def __init__(self, text: str, icon_kind: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._icon_kind = icon_kind
        self._update_icon()
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(42)
        self.setObjectName("nav")

    def enterEvent(self, e):
        if self._shadow is None:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 7)
            shadow.setColor(QColor(0, 0, 0, 140))
            self.setGraphicsEffect(shadow)
            self._shadow = shadow
        super().enterEvent(e)

    def _update_icon(self):
        color = "#ffffff" if self.isChecked() else "#b9c0cd"
        self.setIcon(_icon(self._icon_kind, color, 18))


class TitleBar(QWidget):
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    report_requested = Signal()
    settings_requested = Signal()
    mini_requested = Signal()
    immersive_requested = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._drag = None
        self.setFixedHeight(56)
        self.setObjectName("titlebar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 12, 8)
        lay.setSpacing(8)
        self.page_label = QLabel(tr("正在播放"))
        self.page_label.setObjectName("pagecrumb")
        lay.addWidget(self.page_label)
        lay.addStretch(1)

        for text, icon_name, sig in (
                (tr("迷你模式"), "mini", self.mini_requested),
                (tr("沉浸"), "expand", self.immersive_requested)):
            b = IconButton(text)
            b.setObjectName("quick")
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(_icon(icon_name, "#c9cdd6", 16))
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(sig.emit)
            lay.addWidget(b)

        lay.addSpacing(8)
        self.b_min = self._win_button("min")
        self.b_max = self._win_button("max")
        self.b_close = self._win_button("close")
        self.b_min.clicked.connect(self.minimize_requested.emit)
        self.b_max.clicked.connect(self.maximize_requested.emit)
        self.b_close.clicked.connect(self.close_requested.emit)
        for b in (self.b_min, self.b_max, self.b_close):
            lay.addWidget(b)

    def _win_button(self, kind: str) -> QPushButton:
        b = IconButton()
        b.setObjectName("winclose" if kind == "close" else "winbtn")
        b.setFixedSize(34, 28)
        b.setCursor(Qt.PointingHandCursor)
        b.setProperty("glyph", kind)
        label = {"min": "最小化", "max": "最大化", "close": "关闭"}.get(kind, kind)
        b.setToolTip(self._tr(label))
        b.setAccessibleName(self._tr(label))
        b.paintEvent = lambda e, w=b: self._paint_win(w)
        return b

    def _paint_win(self, b: QPushButton):
        p = QPainter(b)
        p.setRenderHint(QPainter.Antialiasing)
        if b.underMouse():
            p.setBrush(QColor("#e45858") if b.objectName() == "winclose"
                       else QColor(28, 32, 38, 18))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(b.rect().adjusted(1, 1, -1, -1), 7, 7)
        col = QColor("#ffffff") if (b.underMouse() and b.objectName() == "winclose") else QColor("#b6bcc7")
        p.setPen(QPen(col, 1.35, Qt.SolidLine, Qt.RoundCap))
        r = b.rect()
        cx, cy = r.center().x(), r.center().y()
        g = b.property("glyph")
        if g == "min":
            p.drawLine(cx - 5, cy + 3, cx + 5, cy + 3)
        elif g == "max":
            p.drawRoundedRect(QRectF(cx - 5, cy - 5, 10, 10), 1.5, 1.5)
        else:
            p.drawLine(cx - 5, cy - 5, cx + 5, cy + 5)
            p.drawLine(cx + 5, cy - 5, cx - 5, cy + 5)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.maximize_requested.emit()


class Sidebar(QWidget):
    nav_requested = Signal(str)
    recent_requested = Signal(object)

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.setObjectName("sidebar")
        self.setFixedWidth(248)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 18, 16, 16)
        root.setSpacing(8)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel("◉")
        mark.setObjectName("brandmark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(36, 36)
        brand.addWidget(mark)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel("桌面歌词")
        name.setObjectName("brandname")
        sub = QLabel("DESKTOP PLAYER")
        sub.setObjectName("brandsub")
        col.addWidget(name)
        col.addWidget(sub)
        brand.addLayout(col)
        brand.addStretch(1)
        root.addLayout(brand)
        root.addSpacing(8)

        self.status = QLabel("●  " + tr("正在读取系统媒体"))
        self.status.setObjectName("sidestatus")
        root.addWidget(self.status)
        root.addSpacing(12)

        self.buttons = {}
        for key, text, icon_name in (
                ("now", tr("正在播放"), "play"),
                ("report", tr("听歌报告"), "report"),
                ("history", tr("播放历史"), "history"),
                ("settings", tr("桌面歌词设置"), "settings")):
            b = NavButton(text, icon_name)
            b.clicked.connect(lambda _=False, k=key: self.nav_requested.emit(k))
            self.buttons[key] = b
            root.addWidget(b)

        root.addSpacing(18)
        head = QHBoxLayout()
        lb = QLabel(tr("最近播放"))
        lb.setObjectName("sidehead")
        head.addWidget(lb)
        head.addStretch(1)
        self.count = QLabel("0")
        self.count.setObjectName("sidecount")
        head.addWidget(self.count)
        root.addLayout(head)

        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(2)
        root.addLayout(self.recent_box)
        root.addStretch(1)

        tip = QLabel(tr("听歌数据只保存在本机\n不会上传，也不会关联账号"))
        tip.setObjectName("sidetip")
        tip.setWordWrap(True)
        root.addWidget(tip)
        self.set_active("now")

    def set_active(self, key: str):
        for k, b in self.buttons.items():
            b.setChecked(k == key)
            b._update_icon()

    def set_status(self, text: str, live: bool = False):
        self.status.setText(("●  " if live else "○  ") + text)
        self.status.setProperty("live", "1" if live else "0")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def set_recent(self, tracks):
        while self.recent_box.count():
            item = self.recent_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.count.setText(str(len(tracks)))
        if not tracks:
            empty = QLabel(self._tr("暂无播放记录"))
            empty.setObjectName("sideempty")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(54)
            self.recent_box.addWidget(empty)
            return
        for t in tracks[:6]:
            row = QPushButton("%s\n%s" % (t.get("title") or self._tr("未知歌曲"),
                                         t.get("artist") or self._tr("未知歌手")))
            row.setObjectName("recent")
            row.setCursor(Qt.PointingHandCursor)
            row.setMinimumHeight(42)
            row.setToolTip("%s · %s" % (t.get("title", ""),
                                        _format_duration(t.get("seconds", 0), self._tr)))
            row.clicked.connect(lambda _=False, tr_=t: self.recent_requested.emit(tr_))
            self.recent_box.addWidget(row)


class StageBackdrop(QWidget):
    """Paints the cover-tinted wash for the entire now-playing stage."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accent = QColor("#ff7a4d")
        self.cover = None
        self._cover_cache_key = None
        self._cover_cache_pix = None
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def set_cover(self, cover):
        self.cover = cover
        self._cover_cache_key = None
        self.update()

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(STAGE))
        if self.cover is not None and not self.cover.isNull():
            key = (self.cover.cacheKey(), w, h)
            if self._cover_cache_key != key:
                self._cover_cache_pix = self.cover.scaled(
                    max(80, w), max(80, h), Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation)
                self._cover_cache_key = key
            scaled = self._cover_cache_pix
            src = QRectF((scaled.width() - w) / 2.0,
                         (scaled.height() - h) / 2.0, w, h)
            p.setOpacity(0.22)
            p.drawPixmap(QRectF(0, 0, w, h), scaled, src)
            p.setOpacity(1.0)
        wash = QRadialGradient(QPoint(int(w * 0.38), int(h * 0.42)),
                               max(w, h) * 0.62)
        c = QColor(self.accent)
        c.setAlpha(54)
        wash.setColorAt(0.0, c)
        c2 = QColor(self.accent)
        c2.setAlpha(0)
        wash.setColorAt(1.0, c2)
        p.fillRect(0, 0, w, h, wash)
        shade = QLinearGradient(0, 0, 0, h)
        shade.setColorAt(0.0, QColor(7, 9, 12, 95))
        shade.setColorAt(0.52, QColor(7, 9, 12, 120))
        shade.setColorAt(1.0, QColor(7, 9, 12, 190))
        p.fillRect(0, 0, w, h, shade)
        p.end()


class LyricsCanvas(QWidget):
    seek_requested = Signal(float)

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.lines = []
        self.trans = {}
        self.cur_idx = -1
        self.pos = 0.0
        self.accent = QColor("#ff7a4d")
        self.cover = None
        self.playing = False
        self.song = {}
        self._manual = 0.0
        self._manual_until = 0.0
        self._line_h = 64.0
        self._cover_cache_key = None
        self._cover_cache_pix = None
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._font_family = ""
        self._font_cache = {}
        self._content_rect = None

    def set_content_rect(self, x, y, w, h):
        self._content_rect = (int(x), int(y), max(1, int(w)), max(1, int(h)))
        self.update()

    def set_lyrics(self, lines, trans, song=None):
        self.lines = list(lines or [])
        self.trans = dict(trans or {})
        self.song = dict(song or self.song or {})
        self.cur_idx = -1
        self._manual = 0.0
        self.update()

    def set_playback(self, pos, cur_idx, playing, accent=None, cover=None,
                     song=None, font_family=""):
        self.pos = float(pos or 0.0)
        self.cur_idx = int(cur_idx)
        self.playing = bool(playing)
        if accent is not None:
            self.accent = QColor(accent)
        if cover is not None:
            self.cover = cover
            self._cover_cache_key = None
        if song is not None:
            self.song = dict(song)
        if font_family and font_family != self._font_family:
            self._font_family = font_family
            self._font_cache.clear()
        self.update()

    def _font(self, px: int, bold: bool = False) -> QFont:
        key = (px, bold, self._font_family)
        f = self._font_cache.get(key)
        if f is None:
            f = _pick_ui_font(px, bold=bold)
            if self._font_family:
                f.setFamily(self._font_family)
            self._font_cache[key] = f
        return f

    def wheelEvent(self, e):
        self._manual -= e.angleDelta().y() * 0.42
        self._manual_until = time.monotonic() + 4.0
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self.lines:
            return
        _cx, cy, _cw, ch = self._content_geometry()
        idx = self._index_at(e.position().y() - cy, ch)
        if 0 <= idx < len(self.lines):
            self.seek_requested.emit(float(self.lines[idx][0]))

    def _content_geometry(self):
        if self._content_rect is None:
            return 0, 0, self.width(), self.height()
        return self._content_rect

    def _index_at(self, y: float, content_h: float | None = None) -> int:
        base = float(content_h or self.height()) * 0.20
        idx = int(round((y - base) / self._line_h)) + self.cur_idx
        return max(0, min(len(self.lines) - 1, idx))

    def _line_fraction(self, idx: int) -> float:
        if idx < 0 or idx >= len(self.lines):
            return 0.0
        t0 = float(self.lines[idx][0])
        t1 = (float(self.lines[idx + 1][0]) if idx + 1 < len(self.lines)
              else t0 + max(4.0, float(self.song.get("duration") or 8.0)))
        return max(0.0, min(1.0, (self.pos - t0) / max(0.35, t1 - t0)))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        cx, cy, cw, ch = self._content_geometry()
        p.save()
        p.setClipRect(QRectF(cx, cy, cw, ch))
        p.translate(cx, cy)
        w, h = cw, ch

        if not self.lines:
            self._paint_empty(p, w, h)
            p.restore()
            p.end()
            return

        if time.monotonic() > self._manual_until:
            self._manual *= 0.86
            if abs(self._manual) < 0.5:
                self._manual = 0.0

        # The now-playing layout puts the active line near the upper quarter,
        # like a desktop player's lyric pane, not in the vertical centre.
        base = h * 0.20 + self._manual

        first = max(0, self.cur_idx - 2)
        last = min(len(self.lines), self.cur_idx + 6)
        for i in range(first, last):
            dist = i - self.cur_idx
            y = base + dist * self._line_h
            if y < -40 or y > h + 40:
                continue
            text = str(self.lines[i][1] or "")
            if not text.strip():
                continue
            current = (i == self.cur_idx)
            if current:
                self._paint_current(p, text, i, y, w)
            else:
                alpha = max(46, 150 - abs(dist) * 20)
                f = self._font(20 if abs(dist) <= 2 else 17, bold=False)
                p.setFont(f)
                p.setPen(QColor(238, 239, 242, alpha))
                fm = QFontMetrics(f)
                p.drawText(QRectF(24, y - 16, w - 48, 32),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(text, Qt.ElideRight, max(80, w - 48)))
                tr = self.trans.get(i, "")
                if tr and abs(dist) <= 1:
                    tf = self._font(13)
                    p.setFont(tf)
                    p.setPen(QColor(206, 209, 215, max(38, alpha - 60)))
                    fm2 = QFontMetrics(tf)
                    p.drawText(QRectF(24, y + 20, w - 48, 20),
                               Qt.AlignLeft | Qt.AlignVCenter,
                               fm2.elidedText(tr, Qt.ElideRight, max(80, w - 48)))

        p.restore()
        p.end()

    def _paint_current(self, p, text, idx, y, w):
        limit = max(160.0, w - 48)
        size = 34
        while size > 22:
            fm = QFontMetrics(self._font(size, bold=True))
            if fm.horizontalAdvance(text) <= limit:
                break
            size -= 2
        f = self._font(size, bold=True)
        fm = QFontMetrics(f)
        shown = fm.elidedText(text, Qt.ElideRight, limit)
        rect_h = 62 if size >= 30 else 54
        rect = QRectF(24, y - 30, w - 48, rect_h)
        p.setFont(f)
        p.setPen(QColor(245, 246, 248, 84))
        p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
        frac = self._line_fraction(idx)
        if frac > 0.0:
            p.save()
            p.setClipRect(QRectF(rect.left(), rect.top(),
                                 fm.horizontalAdvance(shown) * frac, rect.height()))
            p.setPen(self.accent)
            p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, shown)
            p.restore()
        tr = self.trans.get(idx, "")
        if tr:
            tf = self._font(14)
            p.setFont(tf)
            p.setPen(QColor(215, 218, 224, 170))
            fm2 = QFontMetrics(tf)
            p.drawText(QRectF(24, y + (36 if size >= 30 else 30), w - 48, 22),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       fm2.elidedText(tr, Qt.ElideRight, max(80, w - 48)))

    def _paint_empty(self, p, w, h):
        cy = h * 0.40
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(w / 2.0, cy), 30, 30)
        _draw_icon(p, "note", QRectF(w / 2.0 - 13, cy - 13, 26, 26),
                   QColor(255, 255, 255, 150))
        p.setPen(QColor(255, 255, 255, 225))
        p.setFont(self._font(32, bold=True))
        p.drawText(QRectF(0, cy + 48, w, 46), Qt.AlignCenter,
                   self._tr("等待播放"))
        p.setPen(QColor(255, 255, 255, 150))
        p.setFont(self._font(13))
        p.drawText(QRectF(20, cy + 92, w - 40, 44), Qt.AlignHCenter | Qt.AlignTop,
                   self._tr("在任意接入系统媒体控制的播放器中开始播放"))


class CoverArt(QWidget):
    def __init__(self, size=64, parent=None):
        super().__init__(parent)
        self._size = size
        self.pix = None
        self.setFixedSize(size, size)

    def set_cover(self, pix):
        self.pix = pix
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(r, self.width() * 0.18, self.width() * 0.18)
        p.setClipPath(path)
        if self.pix is not None and not self.pix.isNull():
            p.drawPixmap(r.toRect(), self.pix)
        else:
            g = QLinearGradient(0, 0, self.width(), self.height())
            g.setColorAt(0, QColor("#2c3038"))
            g.setColorAt(1, QColor("#171a20"))
            p.fillRect(r, g)
            _draw_icon(p, "note", QRectF(self.width() * 0.27, self.height() * 0.27,
                                        self.width() * 0.46, self.height() * 0.46),
                       QColor(255, 255, 255, 150))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


class StageCover(CoverArt):
    """Large square artwork used by the now-playing stage."""

    def __init__(self, parent=None):
        super().__init__(64, parent)
        self.setMinimumSize(260, 260)
        self.setMaximumSize(460, 460)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def resizeEvent(self, e):
        side = max(120, min(self.width(), self.height()))
        self.setFixedSize(side, side)
        super().resizeEvent(e)


class NowStage(QWidget):
    play_toggle = Signal()
    prev_requested = Signal()
    next_requested = Signal()
    seek_requested = Signal(float)
    report_requested = Signal()
    immersive_requested = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.setObjectName("stage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.backdrop = StageBackdrop(self)
        self.backdrop.setGeometry(0, 0, self.width(), self.height())
        self.backdrop.lower()
        self.canvas = LyricsCanvas(tr)
        self.canvas.setObjectName("lyricCanvas")
        self.canvas.setAutoFillBackground(False)
        self.canvas.setStyleSheet(
            "QWidget#lyricCanvas{background:transparent;border:none;}")
        self.canvas.setParent(self)
        self.canvas.seek_requested.connect(self.seek_requested.emit)
        self.canvas.setGeometry(0, 0, self.width(), self.height())
        self.canvas.raise_()
        self.canvas.show()
        self._stage_cover = None

        self.source = QLabel(tr("NOW PLAYING"))
        self.source.setObjectName("stageeyebrow")
        self.source.setParent(self)
        self.track_title = QLabel(tr("等待播放"))
        self.track_title.setObjectName("stagetrack")
        self.track_title.setParent(self)
        self.track_artist = QLabel(tr("播放音乐后自动显示歌词"))
        self.track_artist.setObjectName("stageartist")
        self.track_artist.setParent(self)
        self.immersive_btn = QPushButton(tr("沉浸歌词"))
        self.immersive_btn.setObjectName("stageghost")
        self.immersive_btn.setCursor(Qt.PointingHandCursor)
        self.immersive_btn.setIcon(_icon("expand", "#ffffff", 15))
        self.immersive_btn.clicked.connect(self.immersive_requested.emit)
        self.immersive_btn.setParent(self)

        # Match the reference: a smaller square artwork, leaving the majority
        # of the right-hand region to the lyrics.
        self.hero_cover = StageCover(self)
        self.hero_cover.setParent(self)

        self.bar = QFrame(self)
        self.bar.setObjectName("playbar")
        self.bar.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(14, 11, 16, 11)
        bl.setSpacing(12)
        self.cover = CoverArt(54)
        bl.addWidget(self.cover)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        self.title = QLabel(tr("等待播放"))
        self.title.setObjectName("bartitle")
        self.artist = QLabel(tr("播放音乐后自动显示歌词"))
        self.artist.setObjectName("barartist")
        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        bl.addLayout(meta, 1)
        self.b_prev = self._round_button("prev", label="上一首")
        self.b_toggle = self._round_button("play", primary=True, label="播放")
        self.b_next = self._round_button("next", label="下一首")
        self.b_prev.clicked.connect(self.prev_requested.emit)
        self.b_toggle.clicked.connect(self.play_toggle.emit)
        self.b_next.clicked.connect(self.next_requested.emit)
        for b in (self.b_prev, self.b_toggle, self.b_next):
            bl.addWidget(b)
        self.time = QLabel("0:00")
        self.time.setObjectName("bartime")
        self.time.setFixedWidth(92)
        self.time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bl.addWidget(self.time)

        # The play bar uses an absolute-positioned slider below the metadata.
        # It must be a child of the bar, otherwise it is placed relative to the
        # stage and ends up hidden behind the bar in normal window sizes.
        self.slider = QSlider(Qt.Horizontal, self.bar)
        self.slider.setObjectName("progress")
        self.slider.setRange(0, 1000)
        self.slider.setFixedHeight(18)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_drag", True))
        self.slider.sliderReleased.connect(self._release_seek)
        self._drag = False
        self._duration = 0.0

    def _round_button(self, icon_name: str, primary: bool = False,
                      label: str = "") -> QPushButton:
        b = QPushButton()
        b.setObjectName("playprimary" if primary else "playround")
        b.setFixedSize(46 if primary else 38, 46 if primary else 38)
        b.setCursor(Qt.PointingHandCursor)
        if label:
            b.setToolTip(self._tr(label))
            b.setAccessibleName(self._tr(label))
        b.setIcon(_icon(icon_name, "#ffffff", 20 if primary else 17))
        b.setIconSize(QSize(20 if primary else 17, 20 if primary else 17))
        return b

    def _release_seek(self):
        self._drag = False
        if self._duration > 0:
            self.seek_requested.emit(self.slider.value() / 1000.0 * self._duration)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.backdrop.setGeometry(0, 0, self.width(), self.height())
        # The right-hand stage mirrors a full player layout: artwork on the
        # left, lyrics on the right, transport along the bottom. The lyric
        # canvas owns only the text column; it is never covered by artwork.
        if self.width() < 780:
            # Narrow layouts: give lyrics the full stage and put the artwork
            # behind the translucent lyric layer instead of squeezing the text.
            self.hero_cover.hide()
            self.source.move(24, 18)
            self.track_title.move(24, 52)
            self.track_title.resize(max(220, self.width() - 48), 38)
            self.track_artist.move(24, 90)
            self.track_artist.resize(max(220, self.width() - 48), 24)
            self.canvas.setGeometry(0, 0, self.width(), self.height())
            self.canvas.set_content_rect(
                12, 112, max(220, self.width() - 24),
                max(180, self.height() - 112 - 118))
            self.canvas.show()
            self.immersive_btn.adjustSize()
            self.immersive_btn.move(self.width() - self.immersive_btn.width() - 24, 16)
            bar_h = 92
            self.bar.setGeometry(20, self.height() - bar_h - 18,
                                 self.width() - 40, bar_h)
            self.slider.setGeometry(94, 68, max(80, self.bar.width() - 392), 18)
            self.slider.raise_()
            return
        self.hero_cover.show()
        top = 58
        bottom = 118
        gap = 38
        side_margin = 32
        available_h = max(220, self.height() - top - bottom)
        max_cover = max(180, min(360, available_h - 40))
        cover_side = max(180, min(max_cover,
                                  int(self.width() * 0.27), available_h))
        self.hero_cover.setFixedSize(cover_side, cover_side)
        self.hero_cover.move(side_margin + 20,
                             top + max(0, (available_h - cover_side) // 2))
        lyrics_left = side_margin * 2 + cover_side + gap
        self.source.move(side_margin, top + 12)
        header_y = top + 48
        self.track_title.move(lyrics_left, header_y)
        self.track_title.resize(max(180, self.width() - lyrics_left - 30), 38)
        self.track_artist.move(lyrics_left, header_y + 38)
        self.track_artist.resize(max(180, self.width() - lyrics_left - 30), 24)
        lyric_top = top + 124
        self.canvas.setGeometry(0, 0, self.width(), self.height())
        self.canvas.set_content_rect(
            lyrics_left, lyric_top,
            max(220, self.width() - lyrics_left - side_margin),
            max(130, available_h - 124))
        self.canvas.setStyleSheet(
            "QWidget#lyricCanvas{background:transparent;border:none;}")
        self.canvas.show()
        self.immersive_btn.adjustSize()
        self.immersive_btn.move(self.width() - self.immersive_btn.width() - 24, 16)
        bar_h = 92
        self.bar.setGeometry(20, self.height() - bar_h - 18, self.width() - 40, bar_h)
        self.slider.setGeometry(94, 68, max(80, self.bar.width() - 392), 18)
        self.slider.raise_()

    def paintEvent(self, e):
        """The full-stage canvas owns the backdrop.

        Drawing the cover wash here as well creates a visible seam where the
        two independently scaled pixmaps meet. The canvas now covers the whole
        stage and paints it once; the parent only needs an opaque base colour.
        """
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(STAGE))
        p.end()

    def ov_cover_for_paint(self):
        return self._stage_cover

    def update_track(self, song, cover):
        song = song or {}
        self.title.setText(song.get("title") or self._tr("等待播放"))
        artist = song.get("artist") or self._tr("播放音乐后自动显示歌词")
        self.artist.setText(artist)
        self.track_title.setText(self.title.text())
        self.track_artist.setText(artist)
        self.cover.set_cover(cover)
        self.hero_cover.set_cover(cover)
        self.backdrop.set_cover(cover)
        self._stage_cover = cover
        self.update()
        self.slider.setValue(0)
        self._duration = float(song.get("duration") or 0.0)
        self.time.setText("0:00")
        self.canvas.set_playback(self.canvas.pos, self.canvas.cur_idx,
                                 self.canvas.playing, cover=cover, song=song)

    def update_progress(self, pos, duration, playing):
        self._duration = max(0.0, float(duration or 0.0))
        self.canvas.set_playback(pos, self.canvas.cur_idx, playing)
        if not self._drag:
            val = int(min(1.0, max(0.0, pos / self._duration)) * 1000) \
                if self._duration > 0 else 0
            self.slider.blockSignals(True)
            self.slider.setValue(val)
            self.slider.blockSignals(False)
        self.b_toggle.setIcon(_icon("pause" if playing else "play", "#ffffff", 20))
        self.b_toggle.setToolTip(self._tr("暂停") if playing else self._tr("播放"))
        cur = int(max(0, pos))
        if self._duration > 0:
            dur = int(self._duration)
            self.time.setText("%d:%02d / %d:%02d" % (cur // 60, cur % 60,
                                                     dur // 60, dur % 60))
        else:
            self.time.setText("%d:%02d" % (cur // 60, cur % 60))

    def set_accent(self, color):
        self.canvas.accent = QColor(color)
        self.backdrop.set_accent(color)
        a = QColor(color).name()
        self.bar.setStyleSheet(
            "QFrame#playbar{background:qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            "stop:0 rgba(34,38,47,228), stop:1 rgba(16,18,23,232));"
            "border:1px solid rgba(255,255,255,34);border-radius:26px;}"
            "QPushButton#playprimary{background:%s;border:none;border-radius:23px;}"
            "QPushButton#playprimary:hover{background:%s;}"
            "QPushButton#playround{background:rgba(255,255,255,16);border:1px solid rgba(255,255,255,26);"
            "border-radius:19px;}"
            "QPushButton#playround:hover{background:rgba(255,255,255,30);}"
            "QPushButton#playround:pressed{background:rgba(255,255,255,38);}"
            "QPushButton#playprimary:focus{border:2px solid rgba(255,255,255,205);}"
            "QPushButton#playround:focus{border-color:rgba(255,255,255,205);}"
            "QLabel#bartitle{color:#f5f6f8;font-size:14px;font-weight:700;}"
            "QLabel#barartist{color:rgba(235,238,243,185);font-size:12px;}"
            "QLabel#bartime{color:rgba(235,238,243,170);font-size:12px;}"
            "QSlider#progress::groove:horizontal{height:4px;background:rgba(255,255,255,32);border-radius:2px;}"
            "QSlider#progress::sub-page:horizontal{background:%s;border-radius:2px;}"
            "QSlider#progress::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "border-radius:6px;background:#fff;}"
            "QSlider#progress::handle:horizontal:focus{border:2px solid rgba(240,100,58,210);}"
            "QSlider#progress::handle:horizontal:hover{width:12px;height:12px;margin:-5px 0;"
            "border-radius:7px;background:#ffffff;border:1px solid rgba(255,255,255,150);}" %
            (a, QColor(color).lighter(115).name(), a))
        self.hero_cover.setStyleSheet("")


class MiniSparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = [0] * 7
        self.labels = [""] * 7
        self.setMinimumHeight(170)

    def set_data(self, daily):
        # Plot seconds so a valid 20-second session does not collapse to 0.
        self.values = [max(0, int(d.get("seconds", d.get("minutes", 0)) or 0))
                       for d in daily]
        self.labels = [str(d.get("label") or "") for d in daily]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 14, 14, 24, 28
        maxv = max(1, max(self.values))
        n = max(1, len(self.values) - 1)
        pts = []
        for i, v in enumerate(self.values):
            x = left + (w - left - right) * i / n
            y = top + (h - top - bottom) * (1.0 - v / float(maxv))
            pts.append((x, y))
        p.setPen(QPen(QColor(28, 32, 38, 18), 1))
        for i in range(4):
            y = top + (h - top - bottom) * i / 3.0
            p.drawLine(QPoint(int(left), int(y)), QPoint(int(w - right), int(y)))
        if len(pts) >= 2:
            path = QPainterPath()
            path.moveTo(pts[0][0], h - bottom)
            for x, y in pts:
                path.lineTo(x, y)
            path.lineTo(pts[-1][0], h - bottom)
            path.closeSubpath()
            g = QLinearGradient(0, top, 0, h - bottom)
            g.setColorAt(0.0, QColor(240, 100, 58, 72))
            g.setColorAt(1.0, QColor(240, 100, 58, 0))
            p.fillPath(path, g)
            line = QPainterPath()
            line.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                line.lineTo(x, y)
            p.setPen(QPen(QColor(VERMILION), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(line)
            for x, y in pts:
                p.setPen(QPen(QColor("#fffaf3"), 2))
                p.setBrush(QColor(VERMILION))
                p.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
        p.setFont(_pick_ui_font(11))
        p.setPen(QColor(255, 255, 255, 158))
        for i, label in enumerate(self.labels):
            x = left + (w - left - right) * i / n
            p.drawText(QRectF(x - 22, h - 24, 44, 18), Qt.AlignCenter, label)
        p.end()


class SettingsPage(QWidget):
    """Embeds the existing settings surface as a first-class player page."""

    def __init__(self, ov, tr, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        import lyrics_overlay as lo
        self.panel = lo.SettingsPanel(ov, flags=Qt.Widget)
        self.panel.setObjectName("settingsSurface")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.panel)


class StatTile(QFrame):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statTile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        self.value = QLabel("0")
        self.value.setObjectName("statValue")
        self.caption = QLabel(caption)
        self.caption.setObjectName("statCaption")
        lay.addWidget(self.value)
        lay.addWidget(self.caption)

    def set_value(self, text: str):
        self.value.setText(text)


class ReportPage(QWidget):
    clear_requested = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.setObjectName("reportPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 26)
        root.setSpacing(14)
        root.addSpacing(10)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(tr("听歌报告"))
        title.setObjectName("reportTitle")
        sub = QLabel(tr("只统计这台电脑上的真实播放时长"))
        sub.setObjectName("reportSub")
        col.addWidget(title)
        col.addWidget(sub)
        head.addLayout(col)
        head.addStretch(1)
        self.privacy = QLabel(tr("● 仅保存在本机"))
        self.privacy.setObjectName("privacyChip")
        head.addWidget(self.privacy)
        self.clear_btn = QPushButton(tr("清空听歌数据"))
        self.clear_btn.setObjectName("dangerGhost")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        head.addWidget(self.clear_btn)
        root.addLayout(head)

        hero = QFrame()
        hero.setObjectName("reportHero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(22, 18, 22, 12)
        hl.setSpacing(4)
        top = QHBoxLayout()
        self.month_label = QLabel(tr("本月已听"))
        self.month_label.setObjectName("heroCaption")
        top.addWidget(self.month_label)
        top.addStretch(1)
        self.track_count = QLabel("0 " + tr("首"))
        self.track_count.setObjectName("heroChip")
        top.addWidget(self.track_count)
        hl.addLayout(top)
        self.month_value = QLabel("0")
        self.month_value.setObjectName("heroValue")
        hl.addWidget(self.month_value)
        self.month_unit = QLabel(tr("分钟"))
        self.month_unit.setObjectName("heroUnit")
        hl.addWidget(self.month_unit)
        self.spark = MiniSparkline()
        hl.addWidget(self.spark, 1)
        root.addWidget(hero, 1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.today = StatTile(tr("今日听歌时长"))
        self.peak = StatTile(tr("本月最爱时段"))
        self.streak = StatTile(tr("连续听歌"))
        self.active = StatTile(tr("活跃天数"))
        for i, w in enumerate((self.today, self.peak, self.streak, self.active)):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.artist_card = QFrame()
        self.artist_card.setObjectName("reportCard")
        al = QVBoxLayout(self.artist_card)
        al.setContentsMargins(18, 15, 18, 15)
        al.setSpacing(7)
        self.artist_title = QLabel(tr("最常听歌手"))
        self.artist_title.setObjectName("cardHead")
        al.addWidget(self.artist_title)
        self.artist_big = QLabel("—")
        self.artist_big.setObjectName("artistBig")
        al.addWidget(self.artist_big)
        self.artist_meta = QLabel("")
        self.artist_meta.setObjectName("muted")
        al.addWidget(self.artist_meta)
        self.artist_list = QLabel("")
        self.artist_list.setObjectName("rankList")
        self.artist_list.setWordWrap(True)
        self.artist_list.setAlignment(Qt.AlignTop)
        al.addWidget(self.artist_list)
        self.artist_spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        al.addItem(self.artist_spacer)
        bottom.addWidget(self.artist_card, 1)

        self.track_card = QFrame()
        self.track_card.setObjectName("reportCard")
        tl = QVBoxLayout(self.track_card)
        tl.setContentsMargins(18, 15, 18, 15)
        tl.setSpacing(7)
        self.track_title = QLabel(tr("热门歌曲"))
        self.track_title.setObjectName("cardHead")
        tl.addWidget(self.track_title)
        self.track_list = QLabel("")
        self.track_list.setObjectName("trackRank")
        self.track_list.setWordWrap(True)
        self.track_list.setAlignment(Qt.AlignTop)
        tl.addWidget(self.track_list)
        self.track_spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        tl.addItem(self.track_spacer)
        bottom.addWidget(self.track_card, 1)
        root.addLayout(bottom, 1)

        self.empty = QLabel(tr("还没有足够的听歌记录。播放满 20 秒后才会开始统计。"))
        self.empty.setObjectName("reportEmpty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        root.addWidget(self.empty)

    def set_stats(self, s: dict):
        has_data = bool(s.get("total_seconds", s.get("total_minutes")))
        month = int(s.get("month_minutes") or 0)
        if month > 0:
            self.month_value.setText(str(month))
            self.month_unit.setText(self._tr("分钟"))
        else:
            self.month_value.setText(str(int(s.get("month_seconds") or 0)))
            self.month_unit.setText(self._tr("秒"))
        self.track_count.setText("%d %s" % (int(s.get("month_tracks") or 0), self._tr("首")))
        self.today.set_value(_format_duration(s.get("today_seconds", 0), self._tr))
        self.peak.set_value(str(s.get("peak_hour") or "--:--"))
        self.streak.set_value("%d %s" % (int(s.get("streak") or 0), self._tr("天")))
        self.active.set_value("%d %s" % (int(s.get("active_days") or 0), self._tr("天")))
        self.spark.set_data(s.get("daily") or [])
        top = s.get("top_artists") or []
        if top:
            self.artist_big.setText(top[0]["name"])
            self.artist_meta.setText(_format_duration(
                top[0].get("seconds", 0), self._tr))
            self.artist_list.setText("\n".join(
                "%02d   %s   %s" % (i + 1, a["name"],
                                    _format_duration(a.get("seconds", 0), self._tr))
                for i, a in enumerate(top[1:5])))
        else:
            self.artist_big.setText("—")
            self.artist_meta.setText(self._tr("暂无数据"))
            self.artist_list.setText("")
        tracks = s.get("top_tracks") or []
        self.track_list.setText("\n".join(
            "%02d   %s  ·  %s   %s" % (
                i + 1, t["title"], t["artist"],
                _format_duration(t.get("seconds", 0), self._tr))
            for i, t in enumerate(tracks[:7])) or self._tr("暂无数据"))
        self.empty.setVisible(not has_data)
        self.month_value.setVisible(has_data)
        self.month_unit.setVisible(has_data)
        self.track_count.setVisible(has_data)
        self.month_label.setVisible(has_data)
        self.spark.setVisible(has_data)
        self.track_card.setVisible(has_data)
        self.artist_card.setVisible(has_data)
        for tile in (self.today, self.peak, self.streak, self.active):
            tile.setVisible(has_data)
        self.clear_btn.setEnabled(has_data)
        self.privacy.setText(self._tr("● 仅保存在本机") if has_data
                             else self._tr("● 本地统计 · 不上传"))


class HistoryPage(QWidget):
    def __init__(self, tr, loader, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._loader = loader
        self.setObjectName("historyPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 26)
        root.setSpacing(14)
        root.setContentsMargins(28, 22, 28, 28)
        title = QLabel(tr("播放历史"))
        title.setObjectName("reportTitle")
        sub = QLabel(tr("按歌曲聚合；点击一行可查看已缓存的歌词"))
        sub.setObjectName("reportSub")
        root.addWidget(title)
        root.addWidget(sub)
        root.addSpacing(10)
        body = QHBoxLayout()
        body.setSpacing(12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 8, 0)
        # 58 px rows plus 6 px gaps overflowed the viewport by a few pixels and
        # clipped the last row. A 56 px row with 4 px gaps fits four complete
        # rows at the default window size and still leaves the list breathable.
        self.list_lay.setSpacing(4)
        self.scroll.setWidget(self.list_host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body.addWidget(self.scroll, 5)

        self.detail = QFrame()
        self.detail.setObjectName("historyDetail")
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(20, 18, 20, 18)
        dl.setSpacing(6)
        self.d_title = QLabel(tr("选择一首歌"))
        self.d_title.setObjectName("detailTitle")
        self.d_meta = QLabel(tr("历史记录来自本机统计"))
        self.d_meta.setObjectName("muted")
        self.d_stats = QLabel("")
        self.d_stats.setObjectName("detailStats")
        self.d_lyrics = QLabel(tr("选择左侧歌曲，查看缓存在本机的歌词"))
        self.d_lyrics.setObjectName("detailLyrics")
        self.d_lyrics.setWordWrap(True)
        self.d_lyrics.setAlignment(Qt.AlignTop)
        self.d_scroll = QScrollArea()
        self.d_scroll.setWidgetResizable(True)
        self.d_scroll.setFrameShape(QFrame.NoFrame)
        self.d_scroll.setWidget(self.d_lyrics)
        dl.addWidget(self.d_title)
        dl.addWidget(self.d_meta)
        dl.addWidget(self.d_stats)
        dl.addWidget(self.d_scroll, 1)
        body.addWidget(self.detail, 4)
        root.addLayout(body, 1)

    def set_tracks(self, tracks):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not tracks:
            lb = QLabel(self._tr("暂无播放记录"))
            lb.setObjectName("sideempty")
            lb.setAlignment(Qt.AlignCenter)
            lb.setWordWrap(True)
            lb.setMinimumHeight(120)
            self.list_lay.addWidget(lb)
            self.list_lay.addStretch(1)
            self.d_title.setText(self._tr("选择一首歌"))
            self.d_meta.setText(self._tr("历史记录来自本机统计"))
            self.d_stats.setText("")
            self.d_lyrics.setText(self._tr("播放满 20 秒后，歌曲会出现在这里。"))
            return
        for t in tracks[:24]:
            b = QPushButton("%s\n%s   ·   %s   ·   %d %s" % (
                t.get("title") or self._tr("未知歌曲"),
                t.get("artist") or self._tr("未知歌手"),
                _format_duration(t.get("seconds", 0), self._tr),
                int(t.get("plays") or 0), self._tr("次")))
            b.setObjectName("historyRow")
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(60)
            b.setToolTip(self._tr("查看缓存歌词"))
            b.clicked.connect(lambda _=False, row=t: self.show_track(row))
            self.list_lay.addWidget(b)
        self.list_lay.addStretch(1)

    def show_track(self, track):
        self.d_title.setText(track.get("title") or self._tr("未知歌曲"))
        self.d_meta.setText("%s   ·   %s" % (track.get("artist") or self._tr("未知歌手"),
                                             self._tr("仅本机记录")))
        self.d_stats.setText("%s   ·   %d %s   ·   %d %s" % (
            _format_duration(track.get("seconds", 0), self._tr),
            int(track.get("plays") or 0), self._tr("次"),
            int(track.get("days") or 0), self._tr("天")))
        lines, trans = self._loader(track.get("title", ""), track.get("artist", ""))
        if not lines:
            self.d_lyrics.setText(self._tr("这首歌的歌词没有缓存在本机。"))
            return
        rows = []
        for i, (_t, text) in enumerate(lines[:160]):
            rows.append(str(text or ""))
            tr = trans.get(i, "")
            if tr:
                rows.append("    " + str(tr))
        self.d_lyrics.setText("\n".join(rows))


class MainPlayerWindow(QWidget):
    closed = Signal()

    def __init__(self, overlay):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Window)
        self.ov = overlay
        self.setAttribute(Qt.WA_TranslucentBackground)
        try:
            import lyrics_overlay as _lo
            self._tr = _lo._tr
        except Exception:
            self._tr = _identity
        self.setWindowTitle(self._tr("桌面歌词 · 正在播放"))
        self.setMinimumSize(1060, 680)
        self.resize(1260, 820)
        self._page = "now"
        self._immersive = False
        self._last_track = None
        self._last_lines_id = None
        self._last_recent = 0.0
        self._drag = None
        self._build()
        self._apply_style()
        self.refresh_all()
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.shell = QFrame(self)
        self.shell.setObjectName("shell")
        self.shell.setAttribute(Qt.WA_StyledBackground, True)
        root.addWidget(self.shell)
        sl = QVBoxLayout(self.shell)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        self.titlebar = TitleBar(self._tr)
        self.titlebar.minimize_requested.connect(self.showMinimized)
        self.titlebar.maximize_requested.connect(self._toggle_max)
        self.titlebar.close_requested.connect(self.close)
        self.titlebar.mini_requested.connect(self.enter_mini)
        self.titlebar.immersive_requested.connect(self.toggle_immersive)
        sl.addWidget(self.titlebar)

        body = QWidget()
        body.setObjectName("body")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        self.sidebar = Sidebar(self._tr)
        self.sidebar.nav_requested.connect(self.navigate)
        self.sidebar.recent_requested.connect(self.open_history_track)
        bl.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("stack")
        self.now = NowStage(self._tr)
        self.now.play_toggle.connect(lambda: self.ov.media_command("toggle"))
        self.now.prev_requested.connect(lambda: self.ov.media_command("prev"))
        self.now.next_requested.connect(lambda: self.ov.media_command("next"))
        self.now.seek_requested.connect(self._seek)
        self.now.immersive_requested.connect(self.toggle_immersive)
        self.report = ReportPage(self._tr)
        self.report.clear_requested.connect(self._clear_listening)
        self.history = HistoryPage(self._tr, self._load_cached)
        self.settings_page = SettingsPage(self.ov, self._tr)
        self.stack.addWidget(self.now)
        self.stack.addWidget(self.report)
        self.stack.addWidget(self.history)
        self.stack.addWidget(self.settings_page)
        bl.addWidget(self.stack, 1)
        sl.addWidget(body, 1)

        self.grip = QSizeGrip(self.shell)
        self.grip.setFixedSize(18, 18)
        self.grip.raise_()

    def _apply_style(self):
        self.shell.setStyleSheet("""
        * { font-family:"%(font)s"; }
        QFrame#shell { background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                  stop:0 #12161d, stop:0.52 #0d1016,
                                                  stop:1 #080a0f);
                       border:1px solid rgba(255,255,255,34); border-radius:26px; }
        QWidget#body { background:transparent; }
        QWidget#titlebar { background:rgba(10,12,17,188); }
        QLabel#pagecrumb { color:#f3f1ec; font-size:13px; font-weight:750; }
        QPushButton#quick { background:rgba(255,255,255,7); color:#c9cdd6;
                            border:1px solid rgba(255,255,255,18); border-top-color:rgba(255,255,255,34);
                            border-radius:13px; padding:6px 11px; font-size:12px; font-weight:650; }
        QPushButton#quick:hover { background:rgba(255,255,255,16); color:#ffffff;
                                  border-color:rgba(255,255,255,42); }
        QPushButton#quick:pressed { background:rgba(255,255,255,5); }
        QPushButton#winbtn, QPushButton#winclose { background:transparent; border:none; }
        QWidget#sidebar { background:qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                     stop:0 rgba(22,26,34,214),
                                                     stop:1 rgba(11,14,20,224));
                          border-right:1px solid rgba(255,255,255,24); }
        QLabel#brandmark { background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                      stop:0 #ff9a6b, stop:1 %(vermilion)s);
                           color:#fff8ef; border-radius:13px;
                           font-size:19px; font-weight:700; }
        QLabel#brandname { color:#f5f2ec; font-size:17px; font-weight:800; }
        QLabel#brandsub { color:#949bab; font-size:11px; letter-spacing:2px; }
        QLabel#sidestatus { color:#9aa2b2; font-size:12px; padding:2px 4px; }
        QLabel#sidestatus[live="1"] { color:#7ed8a1; }
        QPushButton#nav { text-align:left; padding:0 11px; border:2px solid transparent; border-radius:14px;
                          color:#9aa2b2; font-size:13px; font-weight:650; }
        QPushButton#nav:hover { background:rgba(255,255,255,12); color:#ffffff; }
        QPushButton#nav:pressed { background:rgba(255,255,255,7); color:#f4f6f8; }
        QPushButton#nav:checked { background:qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                             stop:0 %(vermilion)s, stop:1 #c2421f);
                                  color:#fffaf3; }
        QLabel#sidehead { color:#949bab; font-size:11px; font-weight:700;
                          letter-spacing:1px; }
        QLabel#sidecount { color:#8d95a6; font-size:11px; }
        QLabel#sideempty { color:#7f8796; font-size:12px; padding:8px 4px; }
        QPushButton#recent { background:transparent; color:#b6bcc7; border:none;
                             border-left:3px solid transparent; border-radius:11px;
                             padding:7px 9px 7px 11px; text-align:left;
                             font-size:12px; line-height:1.5; }
        QPushButton#recent:hover { background:rgba(255,255,255,10); color:#ffffff;
                                   border-left-color:rgba(240,100,58,190); }
        QLabel#sidetip { color:#7b8393; font-size:11px; line-height:1.55;
                         border-top:1px solid rgba(255,255,255,20); padding-top:10px; }
        QStackedWidget#stack { background:transparent; }
        QWidget#stage { background:#0c0e12; }
        QLabel#stageeyebrow { color:rgba(255,255,255,155); font-size:11px;
                              letter-spacing:2px; font-weight:700; }
        QLabel#stagetrack { color:#f7f4ed; font-size:26px; font-weight:800; }
        QLabel#stageartist { color:rgba(240,238,232,150); font-size:13px; }
        QPushButton#stageghost { background:rgba(255,255,255,14); color:rgba(255,255,255,190);
                                 border:1px solid rgba(255,255,255,22); border-radius:12px;
                                 padding:5px 10px; font-size:12px; }
        QPushButton#stageghost:hover { background:rgba(255,255,255,26); color:#fff; }
        QWidget#reportPage, QWidget#historyPage { background:qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                                             stop:0 #10141b,
                                                                             stop:1 #090b10); }
        QWidget#settingsPage { background:#0c0f15; }
        QLabel#reportTitle { color:#f4f1ea; font-size:26px; font-weight:800; }
        QLabel#reportSub { color:#8f97a7; font-size:13px; }
        QLabel#privacyChip { color:#7ed8a1; background:rgba(126,216,161,16);
                             border:1px solid rgba(126,216,161,44); border-radius:12px;
                             padding:5px 9px; font-size:12px; }
        QPushButton#dangerGhost { background:transparent; color:#ff9d8a;
                                  border:1px solid rgba(255,157,138,72); border-radius:12px;
                                  padding:6px 10px; font-size:12px; }
        QPushButton#dangerGhost:hover { background:#ff9d8a; color:#12151b; }
        QFrame#reportHero { background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                       stop:0 rgba(31,37,48,238),
                                                       stop:1 rgba(15,19,26,242));
                           border:1px solid rgba(255,255,255,32); border-top-color:rgba(255,255,255,50);
                           border-radius:24px; }
        QLabel#heroCaption { color:#9aa2b2; font-size:12px; font-weight:700; }
        QLabel#heroChip { color:#ffb59d; background:rgba(240,100,58,26);
                          border-radius:10px; padding:4px 9px; font-size:11px; }
        QLabel#heroValue { color:#f7f3ea; font-size:56px;
                           font-weight:700; }
        QLabel#heroUnit { color:#8d95a6; font-size:12px; }
        QFrame#statTile, QFrame#reportCard, QFrame#historyDetail {
            background:qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1c222c,
                                       stop:1 #12161d);
            border:1px solid rgba(255,255,255,28); border-top-color:rgba(255,255,255,46);
            border-radius:22px; }
        QLabel#statValue { color:#f2eee6; font-size:27px; font-weight:700; }
        QLabel#statCaption { color:#8f97a7; font-size:11px; }
        QLabel#cardHead { color:#9aa2b2; font-size:11px; font-weight:700; letter-spacing:1px; }
        QLabel#artistBig { color:#f5f1e9; font-size:24px; font-weight:800; }
        QLabel#muted { color:#949bab; font-size:12px; }
        QLabel#rankList, QLabel#trackRank { color:#c1c7d2; font-size:12px; line-height:1.7; }
        QLabel#reportEmpty { color:#949bab; background:rgba(255,255,255,6);
                             border:1px dashed rgba(255,255,255,52); border-radius:20px;
                             font-size:13px; padding:24px; }
        QScrollArea { background:transparent; border:none; }
        QScrollArea > QWidget > QWidget { background:transparent; }
        QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
        QScrollBar::handle:vertical { background:rgba(255,255,255,46); border-radius:4px;
                                      min-height:30px; }
        QScrollBar::handle:vertical:hover { background:rgba(255,255,255,82); }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QPushButton#historyRow { background:rgba(255,255,255,9); color:#eceff4;
                                 border:1px solid rgba(255,255,255,26);
                                 border-radius:18px; padding:9px 12px 9px 15px; text-align:left;
                                 font-size:12px; line-height:1.8;
                                 border-left:3px solid rgba(240,100,58,130); }
        QPushButton#historyRow:hover { border-color:rgba(240,100,58,190);
                                       background:rgba(255,255,255,18); }
        QLabel#detailTitle { color:#f4f1ea; font-size:22px; font-weight:800; }
        QLabel#detailStats { color:#ffb59d; font-size:12px; }
        QLabel#detailLyrics { color:#b9bfc9; font-size:13px; line-height:1.8; }
        QPushButton#nav:focus { border-color:rgba(240,100,58,200); }
        QPushButton#nav:checked:focus { border-color:rgba(255,255,255,210); }
        QPushButton#recent:focus { background:rgba(255,255,255,14); color:#ffffff;
                                   border-left-color:rgba(240,100,58,230); }
        QPushButton#quick:focus, QPushButton#stageghost:focus, QPushButton#dangerGhost:focus {
            border-color:rgba(240,100,58,190); }
        QPushButton#historyRow:focus { border-color:rgba(240,100,58,200); }
        """ % {"paper": PAPER, "paper_deep": PAPER_DEEP, "ink": INK,
               "vermilion": VERMILION, "font": _ui_font_family()})
        self.titlebar.page_label.setStyleSheet(
            "color:#f3f1ec;font-size:14px;font-weight:750;")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "grip"):
            self.grip.move(self.shell.width() - 20, self.shell.height() - 20)
            self.grip.raise_()

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def navigate(self, key: str):
        self._page = key
        self.sidebar.set_active(key)
        if key == "now":
            self.stack.setCurrentWidget(self.now)
            self.titlebar.page_label.setText(self._tr("正在播放"))
        elif key == "report":
            self.stack.setCurrentWidget(self.report)
            self.titlebar.page_label.setText(self._tr("听歌报告"))
            try:
                self.ov.listen_tracker.flush()
            except Exception:
                pass
            self._refresh_report()
        elif key == "history":
            self.stack.setCurrentWidget(self.history)
            self.titlebar.page_label.setText(self._tr("播放历史"))
            self._refresh_history()
        elif key == "settings":
            self.stack.setCurrentWidget(self.settings_page)
            self.titlebar.page_label.setText(self._tr("设置"))

    def open_report(self):
        try:
            self.ov.listen_tracker.flush()
        except Exception:
            pass
        self.navigate("report")

    def open_history_track(self, track):
        self.navigate("history")
        self.history.show_track(track)

    def _open_settings(self):
        self.navigate("settings")

    def enter_mini(self):
        shell = getattr(self.ov, "window_shell", None)
        if shell is not None:
            shell.show_mini()
            return
        self.hide()
        self.ov.show()
        try:
            self.ov.tray.showMessage(self._tr("桌面歌词"), self._tr("已切换到迷你歌词"),
                                     self.ov.tray.Information, 1500)
        except Exception:
            pass

    def toggle_immersive(self):
        self._immersive = not self._immersive
        if self._immersive:
            self.navigate("now")
            self.sidebar.hide()
            self.titlebar.page_label.hide()
            if not self.isFullScreen():
                self.showFullScreen()
        else:
            self.sidebar.show()
            self.titlebar.page_label.show()
            if self.isFullScreen():
                self.showNormal()
            else:
                self.show()
        self.now.immersive_btn.setText(self._tr("退出沉浸") if self._immersive
                                       else self._tr("沉浸歌词"))
        self.now.immersive_btn.adjustSize()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self._immersive:
            self.toggle_immersive()
            return
        if e.key() == Qt.Key_Space:
            self.ov.media_command("toggle")
            return
        if e.key() == Qt.Key_F11:
            self.toggle_immersive()
            return
        super().keyPressEvent(e)

    def _seek(self, seconds):
        try:
            self.ov.seek(seconds)
        except Exception:
            pass

    def _load_cached(self, title: str, artist: str):
        service = getattr(self.ov, "lyrics_service", None)
        if service is not None:
            return service.load_cached(title, artist)
        try:
            import lyrics_overlay as lo
            key = ("%s|%s" % (lo.clean_query_text(title or ""),
                              lo.clean_query_text(artist or ""))).lower().strip()
            path = lo._cache_path(key)
            import json
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            lines = raw.get("lines") or []
            trans_list = raw.get("trans") or []
            trans = {}
            for i, (t0, _txt) in enumerate(lines):
                best, dist = "", 1.2
                for t1, tx in trans_list:
                    d = abs(float(t1) - float(t0))
                    if d < dist:
                        best, dist = tx, d
                if best:
                    trans[i] = best
            return lines, trans
        except Exception:
            return [], {}

    def _clear_listening(self):
        from PySide6.QtWidgets import QMessageBox
        # A Qt test harness may monkeypatch QMessageBox with a plain stub; use
        # the real modal only when the standard-button API is available.
        try:
            box = QMessageBox(self)
        except Exception:
            box = QMessageBox()
        box.setWindowTitle(self._tr("清空听歌数据"))
        box.setText(self._tr("确定删除本机全部听歌统计吗？"))
        box.setInformativeText(self._tr("此操作不可恢复，但不会影响歌词缓存与播放设置。"))
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.setDefaultButton(QMessageBox.Cancel)
        box.setStyleSheet("QMessageBox{background:#161a22;border-radius:18px;}"
                          "QLabel{color:#e5e9f0;font-size:13px;}"
                          "QPushButton{background:#232935;color:#e5e9f0;"
                          "border:1px solid rgba(255,255,255,32);"
                          "border-radius:12px;padding:7px 18px;}"
                          "QPushButton:hover{border-color:#f0643a;color:#ffffff;}")
        if box.exec() != QMessageBox.Yes:
            return
        try:
            self.ov.listen_tracker.flush(final=True, force=True)
            self.ov.listen_store.clear()
            self.ov.listen_tracker.reset()
            self.refresh_all()
        except Exception:
            pass

    def refresh_all(self):
        self._refresh_now(force=True)
        self._refresh_recent()
        self._refresh_report()
        self._refresh_history()

    def _refresh_recent(self):
        try:
            tracks = self.ov.listen_store.recent_tracks(30)
            self.sidebar.set_recent(tracks)
            self._last_recent = time.monotonic()
        except Exception:
            pass

    def _refresh_report(self):
        try:
            # Report is a snapshot, not a session boundary. ListeningTracker
            # persists only the uncommitted delta and counts one play per track.
            self.ov.listen_tracker.flush()
            self.report.set_stats(self.ov.listen_store.stats())
        except Exception:
            pass

    def _refresh_history(self):
        try:
            self.history.set_tracks(self.ov.listen_store.recent_tracks(80))
        except Exception:
            pass

    def on_track_changed(self):
        self._last_track = None
        self._refresh_now(force=True)

    def _refresh_now(self, force: bool = False):
        song = self.ov.song or {}
        title = song.get("title") or ""
        artist = song.get("artist") or ""
        key = (title, artist, id(self.ov.lines), len(self.ov.lines))
        if not force and key == self._last_track:
            return
        self._last_track = key
        self.now.update_track(song, self.ov.cover_pix)
        self.now.set_accent(self.ov.accent1)
        trans = {}
        try:
            trans = self.ov._trans_map or {}
        except Exception:
            pass
        self.now.canvas.set_lyrics(self.ov.lines or [], trans, song)

    def _tick(self):
        try:
            song = self.ov.song or {}
            title = song.get("title") or ""
            if not title:
                self.sidebar.set_status(self._tr("等待系统媒体播放"), False)
                self.now.update_progress(0, 0, False)
                if time.monotonic() - self._last_recent > 8.0:
                    self._refresh_recent()
                return
            self._refresh_now()
            pos = self.ov._current_pos()
            duration = float(self.ov.duration or 0.0)
            playing = self.ov.status == "PLAYING"
            self.now.update_progress(pos, duration, playing)
            idx = -1
            lines = self.ov.lines or []
            lyric_pos = self.ov._lyric_pos()
            for i, (t, _txt) in enumerate(lines):
                if float(t) <= lyric_pos:
                    idx = i
                else:
                    break
            if not lines:
                idx = -1
            if (self.now.canvas.cur_idx != idx or not self.now.canvas.playing
                    or self._page == "now"):
                self.now.canvas.set_playback(lyric_pos, idx, playing,
                                             accent=self.ov.accent1,
                                             cover=self.ov.cover_pix,
                                             song=song,
                                             font_family=self.ov.font_family)
            self.sidebar.set_status(
                "%s · %s" % (self._tr("正在播放") if playing else self._tr("已暂停"),
                             self._tr("歌词已同步")), playing)
            if time.monotonic() - self._last_recent > 10.0:
                self._refresh_recent()
                if self._page == "report":
                    self._refresh_report()
                elif self._page == "history":
                    self._refresh_history()
        except Exception:
            pass

    def closeEvent(self, e):
        try:
            self.ov.listen_tracker.flush(final=True)
        except Exception:
            pass
        self.closed.emit()
        super().closeEvent(e)

