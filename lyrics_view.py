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
import http.client
import ipaddress
import socket
import ssl
import urllib.parse
from collections import OrderedDict
from datetime import datetime

from PySide6.QtCore import (
    QPropertyAnimation, QPoint, QPointF, QRectF, QSize, Qt, QThread, QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QScrollArea, QSizeGrip, QSizePolicy, QSlider, QSpacerItem,
    QStackedWidget, QVBoxLayout,
    QWidget,
)

import ui_theme


INK = "#1c2026"
INK_SOFT = "#6e716f"
PAPER = "#faf8f3"
PAPER_DEEP = "#f2ede4"
VERMILION = "#C2410C"
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


def _format_clock(seconds: float) -> str:
    sec = max(0, int(float(seconds or 0.0)))
    return "%d:%02d" % (sec // 60, sec % 60)


def _format_last_played(timestamp, tr) -> str:
    try:
        moment = datetime.fromtimestamp(float(timestamp or 0.0))
        now = datetime.now()
        if moment.date() == now.date():
            return moment.strftime("%H:%M")
        if moment.year == now.year:
            return moment.strftime("%m-%d %H:%M")
        return moment.strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, TypeError, ValueError):
        return tr("仅本机记录")


def _history_track_adapter(track):
    """Map the local listening record into the history view model.

    Cover, duration, position and source/resume fields are intentionally kept
    optional until the backend contract is delivered. Missing fields remain
    absent instead of being replaced by mock values.
    """
    track = track or {}
    return {
        "title": track.get("title") or "",
        "artist": track.get("artist") or "",
        "seconds": max(0.0, float(track.get("seconds") or 0.0)),
        "plays": max(0, int(track.get("plays") or 0)),
        "days": max(0, int(track.get("days") or 0)),
        "last": track.get("last"),
        "cover": (track.get("cover") or "").strip(),
        "duration": max(0.0, float(track.get("duration") or 0.0)),
        "position": max(0.0, float(track.get("position") or 0.0)),
        "source": (track.get("source") or "").strip(),
        "resume_id": (track.get("resume_id") or "").strip(),
    }


def _playlist_public_addresses(host: str) -> list[tuple[str, int]]:
    """Resolve every A/AAAA record and reject any non-public address."""
    host = (host or "").strip().strip("[]").lower()
    if not host or host in {"localhost", "ip6-localhost", "ip6-loopback"}:
        return []
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return []
    if not infos:
        return []
    addresses = []
    for info in infos:
        if info[0] not in (socket.AF_INET, socket.AF_INET6):
            continue
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return []
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_multicast or address.is_reserved
                or address.is_unspecified):
            return []
        if (info[4][0], info[0]) not in addresses:
            addresses.append((info[4][0], info[0]))
    return addresses


def _playlist_host_is_public(host: str) -> bool:
    """Return whether all resolved records are public HTTP(S) targets."""
    return bool(_playlist_public_addresses(host))


def _safe_playlist_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("unsupported-playlist-url")
    if _playlist_is_platform_url(parsed.hostname):
        raise ValueError("platform-playlist-url")
    if not _playlist_host_is_public(parsed.hostname):
        raise ValueError("private-playlist-host")
    return parsed


def _playlist_is_platform_url(host: str) -> bool:
    host = (host or "").strip().strip("[]").lower()
    platform_hosts = {
        "b23.tv", "bilibili.com", "deezer.com", "joox.com", "kkbox.com",
        "kugou.com", "kuwo.cn", "music.163.com", "music.apple.com",
        "music.youtube.com", "open.spotify.com", "soundcloud.com",
        "tidal.com", "y.qq.com",
    }
    return any(host == item or host.endswith("." + item)
               for item in platform_hosts)


def _fetch_playlist_bytes(url: str, *, timeout: float = 10.0,
                          max_bytes: int = 2 * 1024 * 1024,
                          max_redirects: int = 5) -> bytes:
    """Fetch a playlist document with public-host and size constraints."""
    current = (url or "").strip()
    seen = set()
    for _ in range(max_redirects + 1):
        parsed = _safe_playlist_url(current)
        if current in seen:
            raise ValueError("playlist-redirect-loop")
        seen.add(current)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        pinned_addresses = _playlist_public_addresses(host)
        if not pinned_addresses:
            raise ValueError("private-playlist-host")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(
                host, port, timeout=timeout, context=ssl.create_default_context())
        else:
            connection = _PinnedHTTPConnection(host, port, timeout=timeout)
        connection.pinned_ip = pinned_addresses[0][0]
        try:
            connection.request("GET", path, headers={
                "User-Agent": "Desktop-sing-playlist/1.0",
                "Accept": "audio/x-mpegurl,application/x-mpegurl,text/plain,*/*",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("playlist-redirect-missing")
                current = urllib.parse.urljoin(current, location)
                continue
            if response.status != 200:
                raise ValueError("playlist-http-error")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("playlist-too-large")
            return data
        finally:
            connection.close()
    raise ValueError("playlist-too-many-redirects")


class _PinnedHTTPConnection(http.client.HTTPConnection):
    pinned_ip = ""

    def connect(self):
        address = self.pinned_ip or self.host
        self.sock = self._create_connection(
            (address, self.port), self.timeout, self.source_address)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass


class _PinnedHTTPSConnection(_PinnedHTTPConnection, http.client.HTTPSConnection):
    def connect(self):
        _PinnedHTTPConnection.connect(self)
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(
            self.sock, server_hostname=server_hostname)


def _decode_playlist(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _is_playlist_source_line(line: str) -> bool:
    parsed = urllib.parse.urlparse(line)
    if parsed.scheme in ("http", "https", "file"):
        return bool(parsed.netloc or parsed.path)
    if len(line) >= 3 and line[1] == ":" and line[2] in ("/", "\\"):
        return True
    return (line.startswith(("/", "\\", ".")) or os.path.isabs(line))


def _parse_m3u(text: str) -> list[dict]:
    tracks = []
    seen = set()
    pending = None
    lines = text.splitlines()
    has_m3u_marker = any(
        line.upper().startswith("#EXTM3U") or
        line.upper().startswith("#EXTINF:") for line in lines)
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            metadata = line.split(":", 1)[1]
            duration_text, _, title = metadata.partition(",")
            try:
                duration = max(0.0, float(duration_text))
            except ValueError:
                duration = 0.0
            artist = ""
            if " - " in title:
                artist, title = title.rsplit(" - ", 1)
            pending = {"title": title.strip() or "", "artist": artist.strip(),
                       "duration": duration}
            continue
        if line.startswith("#"):
            continue
        if not has_m3u_marker and not _is_playlist_source_line(line):
            return []
        source_name = os.path.basename(urllib.parse.urlparse(line).path) or line
        track = pending or {"title": "", "artist": "", "duration": 0.0}
        if not track.get("title"):
            track["title"] = source_name
        track["source"] = line
        track_key = ((track.get("title") or "").strip().casefold(),
                     (track.get("artist") or "").strip().casefold())
        if track_key in seen:
            pending = None
            continue
        seen.add(track_key)
        tracks.append(track)
        pending = None
    return tracks


def _playlist_error_message(message: str, tr) -> str:
    message = str(message or "")
    if "platform-playlist-url" in message:
        return tr("这是平台链接。请直接使用 M3U 或 M3U8 链接。")
    if "private-playlist-host" in message:
        return tr("这个地址指向内网或本机，已拒绝。请使用公网 M3U/M3U8 链接。")
    if "playlist-too-large" in message:
        return tr("歌单文件超过大小限制，请导入 2MB 以内的 M3U/M3U8。")
    if "playlist-too-many-tracks" in message:
        return tr("歌单曲目超过 1000 首，请精简后再导入。")
    if "unsupported-playlist-url" in message:
        return tr("无法读取这个歌单。请使用 M3U 或 M3U8 链接。")
    return tr("无法读取歌单，请检查网络或链接后重试。")


def _history_cover_loader(track):
    """Read a cover produced by the shared local cover cache.

    The disk cache is populated by the backend cover pipeline; the UI only
    reads the contract path and never fabricates a hash or file.
    """
    cover_hash = (track.get("cover") or "").strip()
    if not cover_hash:
        return None
    cache = _history_cover_loader._cache
    if cover_hash in cache:
        cache.move_to_end(cover_hash)
        return cache[cover_hash][0]
    path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                        "Desktop-sing", "covers", cover_hash + ".png")
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    estimated_bytes = pixmap.width() * pixmap.height() * 4
    cache[cover_hash] = (pixmap, estimated_bytes)
    while sum(item[1] for item in cache.values()) > 50 * 1024 * 1024:
        cache.popitem(last=False)
    return pixmap


_history_cover_loader._cache = OrderedDict()
_MAX_PLAYLIST_FILE_BYTES = 2 * 1024 * 1024
_MAX_PLAYLIST_TRACKS = 1000


def _is_current_history_track(track, song, current_resume_id=""):
    track = track or {}
    song = song or {}
    resume_id = (track.get("resume_id") or "").strip()
    current_resume_id = (current_resume_id or "").strip()
    if resume_id or current_resume_id:
        return bool(resume_id) and bool(current_resume_id) \
            and resume_id == current_resume_id
    source = (track.get("source") or "").strip()
    if source and song.get("source"):
        return source == (song.get("source") or "").strip()
    return ((track.get("title") or "").strip().lower()
            == (song.get("title") or "").strip().lower()
            and (track.get("artist") or "").strip().lower()
            == (song.get("artist") or "").strip().lower())


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
        self._icon_color = "#b9c0cd"
        self._icon_color_checked = "#ffffff"
        self._update_icon()
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(42)
        self.setObjectName("nav")

    def set_theme(self, theme):
        self._icon_color = theme.text_muted
        self._icon_color_checked = theme.text
        self._update_icon()

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
        color = self._icon_color_checked if self.isChecked() else self._icon_color
        self.setIcon(_icon(self._icon_kind, color, 18))


class _SizeGrip(QSizeGrip):
    """Transparent grip with three dots, kept inside the rounded shell."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        self._dot = QColor(255, 255, 255, 92)

    def set_theme(self, theme):
        self._dot = QColor(theme.grip_dot)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._dot)
        for x, y in ((11, 5), (5, 11), (11, 11)):
            p.drawEllipse(QPointF(x, y), 1.6, 1.6)
        p.end()


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
        self._stats = {}
        self._drag = None
        self._theme = None
        self.setFixedHeight(56)
        self.setObjectName("titlebar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 12, 8)
        lay.setSpacing(8)
        self.page_label = QLabel(tr("正在播放"))
        self.page_label.setObjectName("pagecrumb")
        lay.addWidget(self.page_label)
        lay.addStretch(1)

        self.quick_buttons = {}

        for text, icon_name, sig in (
                (tr("迷你模式"), "mini", self.mini_requested),
                (tr("沉浸"), "expand", self.immersive_requested)):
            key = "mini" if icon_name == "mini" else "immersive"
            b = IconButton(text)
            b.setObjectName("quick")
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(_icon(icon_name, self._quick_color(), 16))
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(sig.emit)
            lay.addWidget(b)
            self.quick_buttons[key] = b

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

    def _quick_color(self) -> str:
        return self._theme.text_muted if self._theme is not None else "#c9cdd6"

    def set_theme(self, theme):
        self._theme = theme
        for key, icon_name in (("mini", "mini"), ("immersive", "expand")):
            self.quick_buttons[key].setIcon(
                _icon(icon_name, self._quick_color(), 16))
        for b in (self.b_min, self.b_max, self.b_close):
            b.update()

    def retranslate(self):
        self.page_label.setText(self._tr("正在播放"))
        self.quick_buttons["mini"].setText(self._tr("迷你模式"))
        self.quick_buttons["immersive"].setText(self._tr("沉浸"))
        self._win_button_labels()

    def _win_button_labels(self):
        labels = {"min": "最小化", "max": "最大化", "close": "关闭"}
        for kind, button in (("min", self.b_min), ("max", self.b_max),
                             ("close", self.b_close)):
            button.setToolTip(self._tr(labels[kind]))
            button.setAccessibleName(self._tr(labels[kind]))

    def _paint_win(self, b: QPushButton):
        p = QPainter(b)
        p.setRenderHint(QPainter.Antialiasing)
        theme = self._theme
        if b.underMouse():
            if b.objectName() == "winclose":
                p.setBrush(QColor(theme.danger if theme is not None else "#e45858"))
            else:
                p.setBrush(QColor(theme.surface_hover if theme is not None
                                  else "rgba(28,32,38,18)"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(b.rect().adjusted(1, 1, -1, -1), 7, 7)
        if b.underMouse() and b.objectName() == "winclose":
            col = QColor("#ffffff")
        else:
            col = QColor(theme.text_secondary if theme is not None else "#b6bcc7")
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
        self._status_key = "正在读取系统媒体"
        self._status_live = False
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
        name = QLabel(tr("桌面歌词"))
        name.setObjectName("brandname")
        self.brand_name = name
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
                ("history", tr("歌单"), "history"),
                ("settings", tr("桌面歌词设置"), "settings")):
            b = NavButton(text, icon_name)
            b.clicked.connect(lambda _=False, k=key: self.nav_requested.emit(k))
            self.buttons[key] = b
            root.addWidget(b)

        root.addSpacing(18)
        self.recent_host = QWidget()
        self.recent_host.setObjectName("recentHost")
        recent_root = QVBoxLayout(self.recent_host)
        recent_root.setContentsMargins(0, 0, 0, 0)
        recent_root.setSpacing(8)
        head = QHBoxLayout()
        lb = QLabel(tr("最近播放"))
        lb.setObjectName("sidehead")
        head.addWidget(lb)
        head.addStretch(1)
        self.count = QLabel("0")
        self.count.setObjectName("sidecount")
        head.addWidget(self.count)
        recent_root.addLayout(head)

        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(2)
        recent_root.addLayout(self.recent_box)
        self.recent_host.hide()
        root.addWidget(self.recent_host)
        root.addStretch(1)

        tip = QLabel(tr("听歌数据只保存在本机\n不会上传，也不会关联账号"))
        tip.setObjectName("sidetip")
        tip.setWordWrap(True)
        root.addWidget(tip)
        self.tip = tip
        self.set_active("now")

    def set_theme(self, theme):
        for b in self.buttons.values():
            b.set_theme(theme)

    def retranslate(self):
        labels = {"now": "正在播放", "report": "听歌报告",
                  "history": "歌单", "settings": "桌面歌词设置"}
        for key, label in labels.items():
            self.buttons[key].setText(self._tr(label))
        self.brand_name.setText(self._tr("桌面歌词"))
        self.tip.setText(self._tr(
            "听歌数据只保存在本机\n不会上传，也不会关联账号"))
        self._apply_status()

    def _apply_status(self):
        self.status.setText(("●  " if self._status_live else "○  ")
                            + self._tr(self._status_key))

    def set_active(self, key: str):
        for k, b in self.buttons.items():
            b.setChecked(k == key)
            b._update_icon()

    def set_status(self, text: str, live: bool = False):
        self._status_key = text
        self._status_live = bool(live)
        self._apply_status()
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
        self._base = QColor(STAGE)
        self._scrim = QColor(7, 9, 12)
        self._dark = True
        self._cover_cache_key = None
        self._cover_cache_pix = None
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def set_theme(self, theme):
        self._base = QColor(theme.bg)
        dark = theme.appearance != "light"
        self._dark = dark
        # The lyric stage stays a deep listening surface in both appearances;
        # white lyric text needs a near-opaque scrim to clear 4.5:1.
        self._scrim = QColor(theme.surface_sunken if dark else theme.text)
        self.update()

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
        p.fillRect(0, 0, w, h, self._base)
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
        c = QColor(self._scrim)
        if self._dark:
            alphas = (95, 120, 190)
        else:
            alphas = (178, 208, 236)
        c.setAlpha(alphas[0])
        shade.setColorAt(0.0, c)
        c.setAlpha(alphas[1])
        shade.setColorAt(0.52, c)
        c.setAlpha(alphas[2])
        shade.setColorAt(1.0, c)
        p.fillRect(0, 0, w, h, shade)
        if self._dark:
            # 2-3% concentric grooves: a quiet vinyl signature in empty space.
            p.setPen(QPen(QColor(255, 255, 255, 7), 1))
            p.setBrush(Qt.NoBrush)
            cx, cy = w * 0.26, h * 0.47
            radius = 46
            limit = max(w, h) * 0.72
            while radius < limit:
                p.drawEllipse(QPointF(cx, cy), radius, radius)
                radius += 18
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
        self.empty_message_key = "等待播放"
        self.empty_description_key = (
            "在任意接入系统媒体控制的播放器中开始播放")
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

    def set_lyrics(self, lines, trans, song=None, *, empty_message_key=None,
                   empty_description_key=None):
        self.lines = list(lines or [])
        self.trans = dict(trans or {})
        self.song = dict(song or self.song or {})
        self.cur_idx = -1
        self._manual = 0.0
        self.empty_message_key = empty_message_key or "等待播放"
        self.empty_description_key = (
            empty_description_key
            or "在任意接入系统媒体控制的播放器中开始播放")
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

    def _translation_rect(self, y: float, w: float) -> QRectF:
        """Keep the current-line translation clear of the next lyric box.

        Non-current lines paint from ``y + 48`` (their box top is
        ``next_y - 16`` with ``_line_h == 64``). The translation therefore has
        to end at ``y + 46`` so there is a 2px visual gap.
        """
        return QRectF(24, y + 24, w - 48, 22)

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
            p.drawText(self._translation_rect(y, w),
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
                   self._tr(self.empty_message_key))
        p.setPen(QColor(255, 255, 255, 150))
        p.setFont(self._font(13))
        p.drawText(QRectF(20, cy + 92, w - 40, 44), Qt.AlignHCenter | Qt.AlignTop,
                   self._tr(self.empty_description_key))


class CoverArt(QWidget):
    def __init__(self, size=64, parent=None):
        super().__init__(parent)
        self._size = size
        self.pix = None
        self._placeholder_top = QColor("#2c3038")
        self._placeholder_bottom = QColor("#171a20")
        self._placeholder_icon = QColor(255, 255, 255, 150)
        self._ring = QColor(255, 255, 255, 28)
        self.setFixedSize(size, size)

    def set_theme(self, theme):
        dark = theme.appearance != "light"
        self._placeholder_top = QColor(theme.surface_raised)
        self._placeholder_bottom = QColor(theme.surface_sunken)
        self._placeholder_icon = QColor(theme.text_muted)
        self._ring = QColor(theme.text)
        self._ring.setAlpha(28 if dark else 40)
        self.update()

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
            g.setColorAt(0, self._placeholder_top)
            g.setColorAt(1, self._placeholder_bottom)
            p.fillRect(r, g)
            _draw_icon(p, "note", QRectF(self.width() * 0.27, self.height() * 0.27,
                                        self.width() * 0.46, self.height() * 0.46),
                       self._placeholder_icon)
        p.setClipping(False)
        p.setPen(QPen(self._ring, 1))
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
        self._theme = None
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
        self._song = {}

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
        self.immersive_btn.setIcon(_icon("expand", self._icon_color(), 15))
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
        b.setIcon(_icon(icon_name, self._on_accent_color(), 20 if primary else 17))
        b.setIconSize(QSize(20 if primary else 17, 20 if primary else 17))
        return b

    def _icon_color(self) -> str:
        if self._theme is not None:
            return self._theme.text
        return "#ffffff"

    def _on_accent_color(self) -> str:
        if self._theme is not None:
            return self._theme.on_accent
        return "#ffffff"

    def set_theme(self, theme):
        self._theme = theme
        self.backdrop.set_theme(theme)
        self.cover.set_theme(theme)
        self.hero_cover.set_theme(theme)
        self.immersive_btn.setIcon(_icon("expand", self._icon_color(), 15))
        playing = self.b_toggle.toolTip() == self._tr("暂停")
        self.b_prev.setIcon(_icon("prev", self._on_accent_color(), 17))
        self.b_toggle.setIcon(_icon("pause" if playing else "play",
                                    self._on_accent_color(), 20))
        self.b_next.setIcon(_icon("next", self._on_accent_color(), 17))
        self.update()

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
            self.slider.setGeometry(20, 68, max(80, self.bar.width() - 40), 18)
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
        self.slider.setGeometry(20, 68, max(80, self.bar.width() - 40), 18)
        self.slider.raise_()

    def paintEvent(self, e):
        """The full-stage canvas owns the backdrop.

        Drawing the cover wash here as well creates a visible seam where the
        two independently scaled pixmaps meet. The canvas now covers the whole
        stage and paints it once; the parent only needs an opaque base colour.
        """
        p = QPainter(self)
        if self._theme is not None:
            p.fillRect(self.rect(), QColor(self._theme.bg))
        else:
            p.fillRect(self.rect(), QColor(STAGE))
        p.end()

    def ov_cover_for_paint(self):
        return self._stage_cover

    def update_track(self, song, cover):
        song = song or {}
        self._song = dict(song)
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

    def retranslate(self):
        self.source.setText(self._tr("NOW PLAYING"))
        song = self._song or {}
        title = song.get("title") or self._tr("等待播放")
        artist = song.get("artist") or self._tr("播放音乐后自动显示歌词")
        self.title.setText(title)
        self.artist.setText(artist)
        self.track_title.setText(title)
        self.track_artist.setText(artist)

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
        """Cover-driven accent: lyric highlight + backdrop wash only.

        Chrome (play bar, buttons, slider) follows the active theme; the lyric
        canvas keeps tracking the album-cover accent as before.
        """
        self.canvas.accent = QColor(color)
        self.backdrop.set_accent(color)
        self.hero_cover.setStyleSheet("")


class MiniSparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values = [0] * 7
        self.labels = [""] * 7
        self._line = QColor(VERMILION)
        self._dot = QColor(VERMILION)
        self._dot_ring = QColor("#fffaf3")
        self._label = QColor(255, 255, 255, 158)
        self.setMinimumHeight(170)

    def set_theme(self, theme):
        self._line = QColor(theme.accent_fill)
        self._dot = QColor(theme.accent_fill)
        self._dot_ring = QColor(theme.surface)
        self._label = QColor(theme.text_muted)
        self.update()

    def set_data(self, daily):
        # Plot seconds so a valid 20-second session does not collapse to 0.
        self.values = [max(0, int(d.get("seconds", d.get("minutes", 0)) or 0))
                       for d in (daily or [])] or [0]
        self.labels = [str(d.get("label") or "") for d in (daily or [])] or [""]
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
            fill_top = QColor(self._line)
            fill_top.setAlpha(72)
            fill_bottom = QColor(self._line)
            fill_bottom.setAlpha(0)
            g.setColorAt(0.0, fill_top)
            g.setColorAt(1.0, fill_bottom)
            p.fillPath(path, g)
            line = QPainterPath()
            line.moveTo(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                line.lineTo(x, y)
            p.setPen(QPen(self._line, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(line)
            for x, y in pts:
                p.setPen(QPen(self._dot_ring, 2))
                p.setBrush(self._dot)
                p.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
        p.setFont(_pick_ui_font(11))
        p.setPen(self._label)
        for i, label in enumerate(self.labels):
            x = left + (w - left - right) * i / n
            p.drawText(QRectF(x - 22, h - 24, 44, 18), Qt.AlignCenter, label)
        p.end()


class SettingsPage(QWidget):
    """Embeds the existing settings surface as a first-class player page."""

    def __init__(self, ov, tr, parent=None):
        super().__init__(parent)
        self.ov = ov
        self._tr = tr
        self.setObjectName("settingsPage")
        import lyrics_overlay as lo
        self.appearance = AppearanceSection(ov, tr, self)
        self.panel = lo.SettingsPanel(ov, flags=Qt.Widget)
        self.panel.setObjectName("settingsSurface")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 0)
        lay.setSpacing(14)
        lay.addWidget(self.appearance)
        lay.addWidget(self.panel)
        self.appearance.refresh()

    def rebuild(self):
        import lyrics_overlay as lo
        old_panel = self.panel
        self.layout().removeWidget(old_panel)
        self.panel = lo.SettingsPanel(self.ov, flags=Qt.Widget)
        self.panel.setObjectName("settingsSurface")
        self.layout().addWidget(self.panel)
        old_panel.deleteLater()
        self.retranslate()

    def retranslate(self):
        self.appearance.retranslate()


class AppearanceSection(QFrame):
    """「外观」section: appearance mode (system/light/dark) + theme swatches.

    Sits at the top of the settings page, above the embedded legacy panel.
    Applies instantly through the shared ThemeManager and persists to cfg.
    """

    _APPEARANCES = ("system", "light", "dark")
    _THEMES = ("ink", "celadon")

    def __init__(self, ov, tr, parent=None):
        super().__init__(parent)
        self.ov = ov
        self._tr = tr
        self.setObjectName("appearanceCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(10)

        head = QVBoxLayout()
        head.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("appearanceTitle")
        self.hint = QLabel()
        self.hint.setObjectName("appearanceHint")
        self.hint.setWordWrap(True)
        head.addWidget(self.title)
        head.addWidget(self.hint)
        root.addLayout(head)

        seg = QHBoxLayout()
        seg.setSpacing(8)
        self.seg_buttons = {}
        for key in self._APPEARANCES:
            b = QPushButton()
            b.setObjectName("appearanceSeg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._pick_appearance(k))
            seg.addWidget(b, 1)
            self.seg_buttons[key] = b
        root.addLayout(seg)

        swatches = QHBoxLayout()
        swatches.setSpacing(10)
        self.swatch_buttons = {}
        for theme_id in self._THEMES:
            b = _ThemeSwatchButton(theme_id, tr)
            b.clicked.connect(lambda _=False, t=theme_id: self._pick_theme(t))
            swatches.addWidget(b, 1)
            self.swatch_buttons[theme_id] = b
        swatches.addStretch(1)
        root.addLayout(swatches)

        motion_row = QHBoxLayout()
        motion_row.setSpacing(8)
        self.motion_btn = QPushButton()
        self.motion_btn.setObjectName("appearanceSeg")
        self.motion_btn.setCheckable(True)
        self.motion_btn.setCursor(Qt.PointingHandCursor)
        self.motion_btn.clicked.connect(self._toggle_motion)
        motion_row.addWidget(self.motion_btn, 0)
        motion_row.addStretch(1)
        root.addLayout(motion_row)
        self.retranslate()

    def _manager(self):
        return getattr(self.ov, "theme_manager", None)

    def _pick_appearance(self, key):
        manager = self._manager()
        if manager is not None:
            manager.set_appearance(key)
        self.ov.cfg["appearance"] = key
        self._save()
        self.refresh()

    def _pick_theme(self, theme_id):
        manager = self._manager()
        if manager is not None:
            manager.set_theme(theme_id)
        self.ov.cfg["theme_id"] = theme_id
        self._save()
        self.refresh()

    def _toggle_motion(self, checked):
        manager = self._manager()
        if manager is not None:
            manager.set_reduce_motion(True if checked else None)
        if checked:
            self.ov.cfg["reduce_motion"] = True
        else:
            self.ov.cfg.pop("reduce_motion", None)
        self._save()
        self.refresh()

    def _save(self):
        try:
            import lyrics_overlay as lo
            lo.save_config(self.ov.cfg)
        except Exception:
            pass

    def refresh(self):
        manager = self._manager()
        appearance = manager.appearance() if manager is not None else \
            str(self.ov.cfg.get("appearance") or "system")
        theme_id = manager.theme_id() if manager is not None else \
            str(self.ov.cfg.get("theme_id") or "ink")
        if appearance not in self._APPEARANCES:
            appearance = "system"
        for key, button in self.seg_buttons.items():
            button.setChecked(key == appearance)
        effective = manager.current().appearance if manager is not None else \
            ("dark" if appearance == "dark" else "light")
        for tid, button in self.swatch_buttons.items():
            button.setChecked(tid == theme_id)
            button.set_appearance(effective)
        reduce_motion = manager.reduce_motion() if manager is not None else \
            bool(self.ov.cfg.get("reduce_motion"))
        self.motion_btn.blockSignals(True)
        self.motion_btn.setChecked(reduce_motion)
        self.motion_btn.blockSignals(False)

    def retranslate(self):
        tr = self._tr
        self.title.setText(tr("外观"))
        self.hint.setText(tr("跟随系统会随 Windows 深浅色切换"))
        for key, label in (("system", "跟随系统"), ("light", "浅色"),
                           ("dark", "深色")):
            self.seg_buttons[key].setText(tr(label))
        for button in self.swatch_buttons.values():
            button.retranslate()
        self.motion_btn.setText(tr("减少动态效果"))
        self.motion_btn.setToolTip(tr("停止页面淡入和过渡动画"))
        self.motion_btn.setAccessibleName(tr("减少动态效果"))


class _ThemeSwatchButton(QPushButton):
    """Theme card: three colour dots (bg/surface/accent) + name + check ring."""

    _NAMES = {"ink": "墨", "celadon": "青瓷"}

    def __init__(self, theme_id, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.theme_id = theme_id
        self._appearance = "dark"
        self.setObjectName("themeSwatch")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(64)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(8)
        self.name = QLabel()
        self.name.setObjectName("themeSwatchName")
        lay.addWidget(self.name)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._dots = []
        for key in ("bg", "surface_raised", "accent_fill"):
            dot = QLabel()
            dot.setObjectName("themeSwatchDots")
            dot.setFixedSize(18, 18)
            row.addWidget(dot)
            self._dots.append((key, dot))
        row.addStretch(1)
        lay.addLayout(row)
        self._paint_dots()
        self.retranslate()

    def set_appearance(self, appearance):
        appearance = "light" if appearance == "light" else "dark"
        if appearance == self._appearance:
            return
        self._appearance = appearance
        self._paint_dots()

    def _paint_dots(self):
        for key, dot in self._dots:
            color = getattr(ui_theme.THEMES[self.theme_id][self._appearance], key)
            dot.setStyleSheet(
                "QLabel#themeSwatchDots{background:%s;border-radius:9px;}" % color)

    def retranslate(self):
        self.name.setText(self._tr(self._NAMES[self.theme_id]))


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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("reportScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.report_body = QWidget()
        self.report_body.setObjectName("reportBody")
        self.report_body.setMinimumHeight(720)
        self.scroll.setWidget(self.report_body)
        outer.addWidget(self.scroll)
        root = QVBoxLayout(self.report_body)
        root.setContentsMargins(28, 22, 28, 26)
        root.setSpacing(14)
        root.addSpacing(10)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = QLabel(tr("听歌报告"))
        self.title.setObjectName("reportTitle")
        self.subtitle = QLabel(tr("只统计这台电脑上的真实播放时长"))
        self.subtitle.setObjectName("reportSub")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
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
        self.hero = hero
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
        self.artist_meta.setObjectName("artistMeta")
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

    def retranslate(self):
        self.title.setText(self._tr("听歌报告"))
        self.subtitle.setText(self._tr("只统计这台电脑上的真实播放时长"))
        self.clear_btn.setText(self._tr("清空听歌数据"))
        self.month_label.setText(self._tr("本月已听"))
        self.month_unit.setText(self._tr("分钟"))
        self.artist_title.setText(self._tr("最常听歌手"))
        self.track_title.setText(self._tr("热门歌曲"))
        self.today.caption.setText(self._tr("今日听歌时长"))
        self.peak.caption.setText(self._tr("本月最爱时段"))
        self.streak.caption.setText(self._tr("连续听歌"))
        self.active.caption.setText(self._tr("活跃天数"))
        self.empty.setText(self._tr("还没有足够的听歌记录。播放满 20 秒后才会开始统计。"))
        if self._stats:
            self.set_stats(self._stats)

    def set_stats(self, s: dict):
        self._stats = s or {}
        has_data = bool(s.get("total_seconds", s.get("total_minutes")))
        month = int(s.get("month_minutes") or 0)
        if month > 0:
            self.month_value.setText(str(month))
            self.month_unit.setText(self._tr("分钟"))
        else:
            self.month_value.setText(str(int(s.get("month_seconds") or 0)))
            self.month_unit.setText(self._tr("秒"))
        month_tracks = int(s.get("month_tracks") or 0)
        self.track_count.setText(
            self._tr("1 首") if month_tracks == 1
            else "%d %s" % (month_tracks, self._tr("首")))
        self.today.set_value(_format_duration(s.get("today_seconds", 0), self._tr))
        self.peak.set_value(str(s.get("peak_hour") or "--:--"))
        streak_days = int(s.get("streak") or 0)
        self.streak.set_value(
            self._tr("1 天") if streak_days == 1
            else "%d %s" % (streak_days, self._tr("天")))
        active_days = int(s.get("active_days") or 0)
        self.active.set_value(
            self._tr("1 天") if active_days == 1
            else "%d %s" % (active_days, self._tr("天")))
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


class HistoryRow(QWidget):
    playbackRequested = Signal(object)

    def __init__(self, track, tr, cover_loader=None, playback_controller=None):
        super().__init__()
        self._tr = tr
        self._cover_loader = cover_loader
        self._track = track
        self._current = False
        self._availability = "unknown"
        self.setObjectName("historyRow")
        self.setProperty("current", "0")
        self.setProperty("external", "0")
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 0)
        root.setSpacing(12)

        self.cover = QLabel("♪")
        self.cover.setObjectName("historyCover")
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setFixedSize(40, 40)
        root.addWidget(self.cover)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        self.title = QLabel(track.get("title") or tr("未知歌曲"))
        self.title.setObjectName("historyTitle")
        self.artist = QLabel(track.get("artist") or tr("未知歌手"))
        self.artist.setObjectName("historyArtist")
        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        root.addLayout(meta, 1)

        self.progress = QLabel("")
        self.progress.setObjectName("historyMeta")
        self.progress.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.progress.setFixedWidth(112)
        root.addWidget(self.progress)
        self.last_played = QLabel("")
        self.last_played.setObjectName("historyMeta")
        self.last_played.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.last_played.setFixedWidth(112)
        root.addWidget(self.last_played)
        self.plays = QLabel("")
        self.plays.setObjectName("historyMeta")
        self.plays.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.plays.setFixedWidth(56)
        root.addWidget(self.plays)

        self.action = QPushButton()
        self.action.setObjectName("historyAction")
        self.action.setFixedSize(28, 28)
        self.action.setIcon(_icon("play", "#ffffff", 14))
        self.action.setIconSize(QSize(14, 14))
        self.action.setVisible(False)
        self.action.clicked.connect(self._request_playback)
        root.addWidget(self.action)

        self._set_cover()
        self.update_playback({"song": {}, "pos": 0.0, "duration": 0.0,
                              "playing": False})

    @property
    def track(self):
        return self._track

    def _set_cover(self):
        pixmap = None
        if callable(self._cover_loader):
            try:
                pixmap = self._cover_loader(self._track)
            except Exception:
                pixmap = None
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self.cover.setPixmap(pixmap.scaled(
                40, 40, Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation))
        else:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("♪")

    def _meta_text(self, pos, duration, playing):
        position = float(self._track.get("position") or 0.0)
        track_duration = float(self._track.get("duration") or 0.0)
        if track_duration > 0.0 and position > 0.0:
            progress = "%s / %s" % (_format_clock(position),
                                    _format_clock(track_duration))
        elif track_duration > 0.0 and position == 0.0:
            progress = self._tr("从头播放")
        elif self._current:
            if duration > 0.0 and pos > 0.0:
                progress = "%s / %s" % (_format_clock(pos),
                                        _format_clock(duration))
            elif pos == 0.0:
                progress = self._tr("从头播放")
            else:
                progress = _format_clock(pos)
        else:
            progress = "—"
        return progress

    def update_playback(self, playback):
        song = playback.get("song") or {}
        current_resume_id = playback.get("current_resume_id") or ""
        current = _is_current_history_track(self._track, song,
                                            current_resume_id)
        external = bool(self._track.get("resume_id")) and not current
        availability = "current" if current else ("external" if external
                                                  else "unknown")
        if availability != self._availability:
            self._availability = availability
            self.setProperty("external", "1" if external else "0")
            self.style().unpolish(self)
            self.style().polish(self)
        self.setEnabled(not external)
        self.cover.setEnabled(not external)
        self.title.setEnabled(not external)
        self.artist.setEnabled(not external)
        self.progress.setEnabled(not external)
        self.last_played.setEnabled(not external)
        self.plays.setEnabled(not external)
        if current != self._current:
            self._current = current
            self.setProperty("current", "1" if current else "0")
            self.style().unpolish(self)
            self.style().polish(self)
            self.setCursor(Qt.PointingHandCursor if current else Qt.ArrowCursor)
        self.action.setVisible(current)
        self.setAccessibleName("%s %s" % (self.title.text(), self.artist.text()))
        if current:
            self.action.setIcon(_icon(
                "pause" if playback.get("playing") else "play",
                "#ffffff", 14))
            self.action.setToolTip(self._tr("播放 / 暂停"))
            self.action.setAccessibleName(self._tr("播放 / 暂停"))
            self.setToolTip("%s · %s" % (self.title.text(), self.artist.text()))
        elif external:
            self.setToolTip(self._tr("在对应播放器中继续"))
        else:
            self.setToolTip("")
        self.progress.setText(self._meta_text(playback.get("pos", 0.0),
                                              playback.get("duration", 0.0),
                                              playback.get("playing", False)))
        self.last_played.setText(_format_last_played(self._track.get("last"),
                                                    self._tr))
        plays = int(self._track.get("plays") or 0)
        self.plays.setText(
            self._tr("1 次") if plays == 1
            else "%d %s" % (plays, self._tr("次")))

    def mousePressEvent(self, e):
        if self._current and e.button() == Qt.LeftButton:
            self._request_playback()
            return
        super().mousePressEvent(e)

    def _request_playback(self):
        if self._current:
            self.playbackRequested.emit(self._track)


class PlaylistFetchThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            data = _fetch_playlist_bytes(self.url)
            tracks = _parse_m3u(_decode_playlist(data))
            if len(tracks) > _MAX_PLAYLIST_TRACKS:
                raise ValueError("playlist-too-many-tracks")
            self.completed.emit(tracks)
        except Exception as exc:
            self.failed.emit(str(exc))


class PlaylistRowButton(QPushButton):
    def __init__(self, track, tr, cover_loader=None, lyrics_loader=None):
        super().__init__()
        self._tr = tr
        self.track = track
        self._cover_loader = cover_loader
        self._lyrics_loader = lyrics_loader
        self.setObjectName("playlistRow")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(56)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 12, 0)
        root.setSpacing(12)
        self.cover = QLabel("♪")
        self.cover.setObjectName("playlistCover")
        self.cover.setFixedSize(40, 40)
        self.cover.setAlignment(Qt.AlignCenter)
        root.addWidget(self.cover)
        meta = QVBoxLayout()
        meta.setSpacing(2)
        self._full_title = track.get("title") or tr("未知歌曲")
        self._full_artist = track.get("artist") or tr("未知歌手")
        self.title = QLabel(self._full_title)
        self.title.setObjectName("playlistTitle")
        self.artist = QLabel(self._full_artist)
        self.artist.setObjectName("playlistArtist")
        self.title.setToolTip(self._full_title)
        self.artist.setToolTip(self._full_artist)
        meta.addWidget(self.title)
        meta.addWidget(self.artist)
        root.addLayout(meta, 1)
        self.duration = QLabel(_format_clock(track.get("duration") or 0.0))
        self.duration.setObjectName("playlistMeta")
        self.duration.setFixedWidth(56)
        self.duration.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self.duration)
        self.status = QLabel(self._status_text())
        self.status.setObjectName("playlistStatus")
        self.status.setProperty("matched", "1" if self._has_local_lyrics()
                                else "0")
        self.status.setFixedWidth(112)
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self.status)
        self._set_cover()
        self._set_accessible_name()

    def _update_metadata_elide(self):
        for label, full in ((self.title, self._full_title),
                            (self.artist, self._full_artist)):
            metrics = QFontMetrics(label.font())
            label.setText(metrics.elidedText(
                full, Qt.ElideMiddle, max(1, label.width())))

    def showEvent(self, event):
        super().showEvent(event)
        self._update_metadata_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_metadata_elide()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
            return
        super().keyPressEvent(event)

    def _set_cover(self):
        pixmap = None
        if callable(self._cover_loader):
            try:
                pixmap = self._cover_loader(self.track)
            except Exception:
                pixmap = None
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self.cover.setPixmap(pixmap.scaled(
                40, 40, Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation))
        else:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("♪")

    def _has_local_lyrics(self):
        if not callable(self._lyrics_loader):
            return False
        try:
            lines, _ = self._lyrics_loader(self.track.get("title", ""),
                                           self.track.get("artist", ""))
        except Exception:
            lines = []
        return bool(lines)

    def _status_text(self):
        if self._has_local_lyrics():
            return "✓ " + self._tr("歌词已就绪")
        return self._tr("未找到本地歌词")

    def _update_status_state(self):
        matched = self._has_local_lyrics()
        self.status.setProperty("matched", "1" if matched else "0")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(self._status_text())

    def _set_accessible_name(self):
        self.setAccessibleName("%s，%s，%s，%s" % (
            self._full_title, self._full_artist,
            self.duration.text(), self.status.text()))

    def retranslate(self):
        self._full_title = self.track.get("title") or self._tr("未知歌曲")
        self._full_artist = self.track.get("artist") or self._tr("未知歌手")
        self.title.setToolTip(self._full_title)
        self.artist.setToolTip(self._full_artist)
        self._update_metadata_elide()
        self.duration.setText(_format_clock(self.track.get("duration") or 0.0))
        self._update_status_state()
        self._set_accessible_name()


class PlaylistPage(QWidget):
    track_selected = Signal(object)

    def __init__(self, tr, parent=None, cover_loader=None, lyrics_loader=None):
        super().__init__(parent)
        self._tr = tr
        self._cover_loader = cover_loader
        self._lyrics_loader = lyrics_loader
        self._tracks = []
        self._state = "empty"
        self._selected_track = None
        self._fetch_thread = None
        self._cancelled = False
        self.setObjectName("playlistPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 28)
        root.setSpacing(16)

        self.title = QLabel(tr("歌单"))
        self.title.setObjectName("playlistPageTitle")
        self.subtitle = QLabel(tr("导入歌单信息，选择曲目后进入歌词页。"))
        self.subtitle.setObjectName("playlistSubtitle")
        root.addWidget(self.title)
        root.addWidget(self.subtitle)

        panel = QFrame()
        panel.setObjectName("playlistPanel")
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(16, 16, 16, 12)
        panel_lay.setSpacing(12)
        form = QHBoxLayout()
        form.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setObjectName("playlistInput")
        self.url_input.setPlaceholderText(tr("粘贴 M3U/M3U8 歌单链接"))
        self.url_input.setAccessibleName(self.url_input.placeholderText())
        self.url_input.setAccessibleDescription(
            self.url_input.placeholderText())
        self.url_input.setFixedHeight(40)
        self.url_input.returnPressed.connect(self._import_url)
        form.addWidget(self.url_input, 1)
        self.import_btn = QPushButton(tr("导入歌单"))
        self.import_btn.setObjectName("primary")
        self.import_btn.setFixedHeight(40)
        self.import_btn.clicked.connect(self._import_url)
        form.addWidget(self.import_btn)
        self.file_btn = QPushButton(tr("从文件导入…"))
        self.file_btn.setObjectName("ghost")
        self.file_btn.setFixedHeight(40)
        self.file_btn.clicked.connect(self._import_file)
        form.addWidget(self.file_btn)
        self.cancel_btn = QPushButton(tr("取消"))
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setFixedHeight(40)
        self.cancel_btn.clicked.connect(self._cancel_import)
        self.cancel_btn.hide()
        form.addWidget(self.cancel_btn)
        panel_lay.addLayout(form)
        self.compliance = QLabel(tr("仅导入歌单信息，不获取音乐音频或版权歌词。"))
        self.compliance.setObjectName("playlistCompliance")
        self.compliance.setWordWrap(True)
        panel_lay.addWidget(self.compliance)
        self.error = QLabel("")
        self.error.setObjectName("playlistError")
        self.error.setWordWrap(True)
        self.error.hide()
        panel_lay.addWidget(self.error)
        self.success = QLabel("")
        self.success.setObjectName("playlistSuccess")
        self.success.setWordWrap(True)
        self.success.hide()
        panel_lay.addWidget(self.success)
        root.addWidget(panel)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.section = QLabel(tr("我的歌单"))
        self.section.setObjectName("playlistSection")
        head.addWidget(self.section)
        head.addStretch(1)
        self.count = QLabel("0")
        self.count.setObjectName("playlistCount")
        head.addWidget(self.count)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.list_host = QWidget()
        self.list_lay = QVBoxLayout(self.list_host)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(0)
        self.scroll.setWidget(self.list_host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        self.setTabOrder(self.url_input, self.import_btn)
        self.setTabOrder(self.import_btn, self.file_btn)
        self._show_empty()

    def _clear_list(self):
        while self.list_lay.count():
            item = self.list_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _show_empty(self):
        card = QFrame()
        card.setObjectName("playlistEmpty")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 36, 24, 36)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignCenter)
        icon = QLabel("♪")
        icon.setObjectName("playlistEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        title = QLabel(self._tr("还没有歌单"))
        title.setObjectName("playlistEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        desc = QLabel(self._tr("导入你自己的播放列表，选择曲目后进入歌词页。"))
        desc.setObjectName("playlistEmptyDesc")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        button = QPushButton(self._tr("导入歌单"))
        button.setObjectName("primary")
        button.setFixedHeight(40)
        button.clicked.connect(self._import_file)
        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(desc)
        lay.addWidget(button)
        self.list_lay.addWidget(card)
        self.list_lay.addStretch(1)

    @staticmethod
    def _track_key(track):
        track = track or {}
        return ((track.get("source") or "").strip(),
                track.get("title") or "",
                track.get("artist") or "",
                float(track.get("duration") or 0.0))

    def _set_selected(self, track):
        self._selected_track = track

    def _row_is_selected(self, track):
        if self._selected_track is None:
            return False
        return self._track_key(track) == self._track_key(self._selected_track)

    def _set_import_ready(self):
        self.url_input.setProperty("error", "0")
        self.url_input.style().unpolish(self.url_input)
        self.url_input.style().polish(self.url_input)
        self.import_btn.setEnabled(True)
        self.file_btn.setEnabled(True)
        self.import_btn.setText(self._tr("导入歌单"))
        self.cancel_btn.hide()

    def set_tracks(self, tracks):
        self._tracks = list(tracks or [])
        self._state = "tracks" if self._tracks else "empty"
        self.error.hide()
        self._set_import_ready()
        self._clear_list()
        self.count.setText(str(len(self._tracks)))
        if self._tracks:
            if len(self._tracks) == 1:
                self.success.setText(self._tr("已导入 1 首曲目"))
            else:
                self.success.setText(
                    self._tr("已导入 %d 首曲目") % len(self._tracks))
            self.success.show()
        else:
            self.success.hide()
        if not self._tracks:
            self._show_empty()
            return
        for track in self._tracks:
            row = PlaylistRowButton(track, self._tr, self._cover_loader,
                                    self._lyrics_loader)
            row.setChecked(self._row_is_selected(track))
            row.clicked.connect(lambda checked=False, row_=row:
                                self._select_row(row_))
            self.list_lay.addWidget(row)
        self.list_lay.addStretch(1)

    def _select_row(self, row):
        self._set_selected(row.track)
        for item_index in range(self.list_lay.count()):
            sibling = self.list_lay.itemAt(item_index).widget()
            if isinstance(sibling, PlaylistRowButton):
                sibling.setChecked(sibling is row)
        self.track_selected.emit(row.track)

    def set_loading(self):
        self._state = "loading"
        self.error.hide()
        self.url_input.setProperty("error", "0")
        self.url_input.style().unpolish(self.url_input)
        self.url_input.style().polish(self.url_input)
        self.import_btn.setEnabled(False)
        self.file_btn.setEnabled(False)
        self.import_btn.setText(self._tr("正在导入…"))
        self.cancel_btn.show()
        self._clear_list()
        for _ in range(3):
            skeleton = QFrame()
            skeleton.setObjectName("playlistSkeleton")
            skeleton.setFixedHeight(56)
            lay = QHBoxLayout(skeleton)
            lay.setContentsMargins(12, 0, 12, 0)
            lay.setSpacing(12)
            cover = QLabel()
            cover.setObjectName("playlistSkeletonCover")
            cover.setFixedSize(40, 40)
            lines = QVBoxLayout()
            lines.setSpacing(8)
            first = QLabel()
            first.setObjectName("playlistSkeletonLine")
            first.setFixedHeight(12)
            second = QLabel()
            second.setObjectName("playlistSkeletonLine")
            second.setFixedHeight(12)
            lines.addWidget(first)
            lines.addWidget(second)
            lay.addWidget(cover)
            lay.addLayout(lines, 1)
            self.list_lay.addWidget(skeleton)
        self.list_lay.addStretch(1)

    def set_error(self, text):
        self.set_tracks([])
        self._state = "error"
        self.url_input.setProperty("error", "1")
        self.url_input.style().unpolish(self.url_input)
        self.url_input.style().polish(self.url_input)
        self.error.setText(text)
        self.error.show()

    def _cancel_import(self):
        self._cancelled = True
        if self._fetch_thread is not None:
            try:
                self._fetch_thread.completed.disconnect(
                    self._on_fetch_completed)
                self._fetch_thread.failed.disconnect(self._on_fetch_failed)
            except (RuntimeError, TypeError):
                pass
            self._fetch_thread = None
        self.set_tracks([])

    def refresh(self):
        if self._state == "loading":
            self.set_loading()
        elif self._state == "tracks":
            self.set_tracks(self._tracks)
        elif self._state == "error":
            self.set_error(self.error.text())
        else:
            self._clear_list()
            self._show_empty()

    def retranslate(self):
        self.title.setText(self._tr("歌单"))
        self.subtitle.setText(self._tr("导入歌单信息，选择曲目后进入歌词页。"))
        self.url_input.setPlaceholderText(self._tr("粘贴 M3U/M3U8 歌单链接"))
        self.url_input.setAccessibleName(self.url_input.placeholderText())
        self.url_input.setAccessibleDescription(self.url_input.placeholderText())
        self.import_btn.setText(self._tr("导入歌单"))
        self.file_btn.setText(self._tr("从文件导入…"))
        self.cancel_btn.setText(self._tr("取消"))
        self.compliance.setText(self._tr(
            "仅导入歌单信息，不获取音乐音频或版权歌词。"))
        self.section.setText(self._tr("我的歌单"))
        if self._state == "loading":
            self.set_loading()
        elif self._state == "tracks":
            self.set_tracks(self._tracks)
        elif self._state == "error":
            self.set_error(self.error.text())
        else:
            self._clear_list()
            self._show_empty()

    def _import_url(self):
        url = self.url_input.text().strip()
        if not url:
            self.set_error(self._tr("无法读取这个歌单。请使用 M3U 或 M3U8 链接。"))
            return
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            self.set_error(self._tr("无法读取这个歌单。请使用 M3U 或 M3U8 链接。"))
            return
        if _playlist_is_platform_url(parsed.hostname or ""):
            self.set_error(self._tr("这是平台链接。请直接使用 M3U 或 M3U8 链接。"))
            return
        self._cancelled = False
        self.set_loading()
        self._fetch_thread = PlaylistFetchThread(url, self)
        self._fetch_thread.completed.connect(self._on_fetch_completed)
        self._fetch_thread.failed.connect(self._on_fetch_failed)
        self._fetch_thread.start()

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self._tr("选择歌单文件"), "",
            "M3U playlist (*.m3u *.m3u8);;All files (*)")
        if not path:
            return
        try:
            if os.path.getsize(path) > _MAX_PLAYLIST_FILE_BYTES:
                self.set_error(self._tr(
                    "歌单文件超过大小限制，请导入 2MB 以内的 M3U/M3U8。"))
                return
        except OSError:
            pass
        try:
            with open(path, "rb") as handle:
                tracks = _parse_m3u(_decode_playlist(handle.read()))
        except OSError:
            tracks = []
        if len(tracks) > _MAX_PLAYLIST_TRACKS:
            self.set_error(self._tr("歌单曲目超过 1000 首，请精简后再导入。"))
            return
        if not tracks:
            self.set_error(self._tr("无法读取这个歌单。请使用 M3U 或 M3U8 链接。"))
            return
        self.set_tracks(tracks)

    def _on_fetch_completed(self, tracks):
        self._fetch_thread = None
        self._set_import_ready()
        if self._cancelled:
            return
        if not tracks:
            self.set_error(self._tr("无法读取这个歌单。请使用 M3U 或 M3U8 链接。"))
            return
        self.set_tracks(tracks)

    def _on_fetch_failed(self, message):
        self._fetch_thread = None
        self._set_import_ready()
        if self._cancelled:
            return
        self.set_error(_playlist_error_message(message, self._tr))


HistoryPage = PlaylistPage
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
        self._setup_theme_manager()
        self.setWindowTitle(self._tr("桌面歌词 · 正在播放"))
        self.setMinimumSize(1060, 680)
        self.resize(1260, 820)
        self._page = "now"
        self._immersive = False
        self._last_track = None
        self._last_lines_id = None
        self._last_recent = 0.0
        self._playlist_track = None
        self._drag = None
        self._build()
        self._apply_style()
        self.refresh_all()
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _setup_theme_manager(self):
        manager = getattr(self.ov, "theme_manager", None)
        reduce_motion = True if self.ov.cfg.get("reduce_motion") else None
        if manager is None:
            theme_id = str(self.ov.cfg.get("theme_id") or "ink")
            appearance = str(self.ov.cfg.get("appearance") or "system")
            if theme_id not in ui_theme.THEMES:
                theme_id = "ink"
            if appearance not in ui_theme.APPEARANCES:
                appearance = "system"
            manager = ui_theme.ThemeManager(
                theme_id, appearance, self, reduce_motion=reduce_motion)
            self.ov.theme_manager = manager
        else:
            manager.set_reduce_motion(reduce_motion)
        self._theme_manager = manager
        manager.changed.connect(self._apply_theme)

    def _release_theme_manager(self):
        manager = getattr(self, "_theme_manager", None)
        if manager is not None:
            try:
                manager.changed.disconnect(self._apply_theme)
            except (RuntimeError, TypeError):
                pass

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
        self.playlist = PlaylistPage(
            self._tr,
            cover_loader=_history_cover_loader,
            lyrics_loader=self._playlist_lyrics_loader)
        self.history = self.playlist
        self.playlist.track_selected.connect(self._open_playlist_track)
        self.settings_page = SettingsPage(self.ov, self._tr)
        self.stack.addWidget(self.now)
        self.stack.addWidget(self.report)
        self.stack.addWidget(self.history)
        self.stack.addWidget(self.settings_page)
        bl.addWidget(self.stack, 1)
        sl.addWidget(body, 1)

        self.grip = _SizeGrip(self.shell)
        self.grip.raise_()

    def _apply_style(self):
        manager = getattr(self.ov, "theme_manager", None)
        theme = manager.current() if manager is not None else ui_theme.THEMES["ink"]["dark"]
        self.shell.setStyleSheet(ui_theme.build_qss(theme, "main"))
        self._push_theme(theme)

    def _push_theme(self, theme):
        for widget in (self.titlebar, self.sidebar, self.now, self.grip):
            setter = getattr(widget, "set_theme", None)
            if callable(setter):
                setter(theme)
        self.report.spark.set_theme(theme)

    def _apply_theme(self, theme):
        self._apply_style()
        self._refresh_now(force=True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "grip"):
            self.grip.move(self.shell.width() - 28, self.shell.height() - 28)
            self.grip.raise_()

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def retranslate_ui(self):
        self.setWindowTitle(self._tr("桌面歌词 · 正在播放"))
        self.titlebar.retranslate()
        self.sidebar.retranslate()
        self.now.retranslate()
        self.report.retranslate()
        self.history.retranslate()
        self.settings_page.rebuild()
        self.settings_page.retranslate()
        self.now.immersive_btn.setText(
            self._tr("退出沉浸") if self._immersive else self._tr("沉浸歌词"))
        self.now.immersive_btn.adjustSize()
        self.now.immersive_btn.move(
            self.now.width() - self.now.immersive_btn.width() - 24, 16)
        self.navigate(self._page)

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
            self.titlebar.page_label.setText(self._tr("歌单"))
            self.playlist.refresh()
            self._refresh_history()
        elif key == "settings":
            self.stack.setCurrentWidget(self.settings_page)
            self.titlebar.page_label.setText(self._tr("设置"))
        self._animate_page(self.stack.currentWidget())

    def _animate_page(self, page):
        if page is None:
            return
        manager = getattr(self, "_theme_manager", None)
        duration = manager.duration("m_base") if manager is not None else 180
        effect = page.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
        old = getattr(page, "_page_anim", None)
        if old is not None:
            try:
                old.stop()
            except RuntimeError:
                pass
        if duration <= 0:
            page.setGraphicsEffect(None)
            return
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda p=page: self._finish_page_anim(p))
        anim.start()
        page._page_anim = anim

    def _finish_page_anim(self, page):
        """Drop the opacity effect once the fade ends.

        Keeping an opacity effect attached at 1.0 forces Qt to render the
        page through an offscreen surface, which blurs text and can leave
        stale child-widget ghosts in grabs.
        """
        page._page_anim = None
        if page.graphicsEffect() is not None:
            page.setGraphicsEffect(None)

    def open_report(self):
        try:
            self.ov.listen_tracker.flush()
        except Exception:
            pass
        self.navigate("report")

    def open_history_track(self, track):
        self.navigate("history")

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

    def _current_resume_id(self):
        provider = getattr(self.ov, "current_resume_id", None)
        try:
            return str(provider() or "") if callable(provider) else ""
        except Exception:
            return ""

    def _playlist_lyrics_loader(self, title: str, artist: str):
        service = getattr(self.ov, "lyrics_service", None)
        if callable(getattr(service, "load_cached", None)):
            return service.load_cached(title, artist)
        return [], {}

    def _open_playlist_track(self, track):
        self._playlist_track = track
        self.navigate("now")
        self._refresh_now(force=True)

    def _resume_current_session(self, track):
        track = track or {}
        resume_id = (track.get("resume_id") or "").strip()
        if resume_id:
            current_resume_id = self._current_resume_id()
            if not current_resume_id or resume_id != current_resume_id:
                return
            position = max(0.0, float(track.get("position") or 0.0))
            if position > 0.0:
                self.ov.seek(position)
            if self.ov.status != "PLAYING":
                self.ov.media_command("toggle")
            return
        if _is_current_history_track(track, self.ov.song or {}):
            self.ov.media_command("toggle")

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
        manager = getattr(self.ov, "theme_manager", None)
        theme = manager.current() if manager is not None else \
            ui_theme.THEMES["ink"]["dark"]
        box.setStyleSheet(ui_theme.build_qss(theme, "overlay"))
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
            self.playlist.refresh()
        except Exception:
            pass

    def on_track_changed(self):
        self._last_track = None
        self._playlist_track = None
        self._refresh_now(force=True)

    def _refresh_now(self, force: bool = False):
        song = self._playlist_track or self.ov.song or {}
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
        if self._playlist_track:
            lines, trans = self._playlist_lyrics_loader(title, artist)
            if lines:
                empty_message_key = "正在播放"
                empty_description_key = ""
            else:
                empty_message_key = "未找到本地歌词"
                empty_description_key = "请添加本地歌词文件后再试。"
            self.now.canvas.set_lyrics(lines, trans, song,
                                       empty_message_key=empty_message_key,
                                       empty_description_key=empty_description_key)
        else:
            self.now.canvas.set_lyrics(
                self.ov.lines or [], trans, song,
                empty_message_key="等待播放",
                empty_description_key="在任意接入系统媒体控制的播放器中开始播放")

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
        self._release_theme_manager()
        self.closed.emit()
        super().closeEvent(e)

