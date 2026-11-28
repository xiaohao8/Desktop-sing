# -*- coding: utf-8 -*-
"""Main player window for Desktop-sing.

The desktop lyric bar stays available as mini mode. This module owns the larger
player experience: library navigation, a full lyric stage, local listening
history and the on-device report.
"""
from __future__ import annotations

import math
import os
import threading
import time
import http.client
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import urllib.parse
from collections import OrderedDict
from datetime import datetime

from PySide6.QtCore import (
    QEvent, QPropertyAnimation, QPoint, QPointF, QRectF, QSize, Qt, QThread,
    QTimer, Signal,
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

import ui_glass
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


def _tc(value, fallback="#888888"):
    """主题令牌是 CSS 字符串（rgba(...)），QColor("rgba(...)") 会静默解析成
    纯黑（alpha=255）——浅色界面上那些「黑印」就是这么来的。绘制取色统一
    走这里，交给能解析 rgba 的解析器。"""
    return ui_glass.qcolor(value, fallback)


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
        # 公网单播才放行：is_global 已排除 loopback/link-local/private/
        # CGNAT(100.64.0.0/10)/保留段；多播单独再拦一次。
        if not address.is_global or address.is_multicast:
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
        "163cn.tv", "b23.tv", "bilibili.com", "deezer.com", "h5.nf.migu.cn",
        "joox.com", "kkbox.com", "kugou.com", "kuwo.cn", "music.163.com",
        "music.apple.com", "music.migu.cn", "music.youtube.com",
        "open.spotify.com", "soundcloud.com", "tidal.com", "y.qq.com",
    }
    return any(host == item or host.endswith("." + item)
               for item in platform_hosts)


_QQ_PLAYLIST_HOSTS = (
    "y.qq.com", "i.y.qq.com", "c.y.qq.com", "u.y.qq.com", "c6.y.qq.com",
)
# Public playlist protocol references (metadata endpoints only):
# - NetEase: api-enhanced (MIT), /api/v6/playlist/detail
# - Kugou: MakcRe/KuGouMusicApi (MIT), gateway signature + pubsongs v2
# - Kuwo: kuwoMusicApi (Apache-2.0), m.kuwo.cn newh5app wapi
# - Migu: MiguMusicApi (protocol reference), MIGUM3.0 playlist songs
_NETEASE_PLAYLIST_HOSTS = (
    "music.163.com", "y.music.163.com", "163cn.tv",
)
_KUGOU_PLAYLIST_HOSTS = ("kugou.com",)
_KUWO_PLAYLIST_HOSTS = ("kuwo.cn",)
_MIGU_PLAYLIST_HOSTS = ("music.migu.cn", "h5.nf.migu.cn")
_MIGU_API_HOSTS = ("app.c.nf.migu.cn",)
_KUGOU_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
_KUGOU_APP_ID = 1005
_KUGOU_CLIENT_VERSION = 20489
_KUGOU_SIGN_SALT = "OIlwieks28dk2k092lksi2UIkp"
_KUGOU_MID = os.urandom(16).hex()
_KUGOU_ANDROID_UA = "Android15-1070-11083-46-0-DiscoveryDRADProtocol-wifi"
_PLAYLIST_URL_RE = re.compile(
    r"https?://[^\s<>\"'，。！？、；：（）【】《》]+", re.IGNORECASE)


def _host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    host = (host or "").strip().strip("[]").lower()
    return any(host == item or host.endswith("." + item)
               for item in suffixes)


def _qq_playlist_host(host: str) -> bool:
    """Only official QQ Music share/API hosts may be fetched."""
    return _host_matches(host, _QQ_PLAYLIST_HOSTS)


def _netease_playlist_host(host: str) -> bool:
    return _host_matches(host, _NETEASE_PLAYLIST_HOSTS)


def _kugou_playlist_host(host: str) -> bool:
    return _host_matches(host, _KUGOU_PLAYLIST_HOSTS)


def _kuwo_playlist_host(host: str) -> bool:
    return _host_matches(host, _KUWO_PLAYLIST_HOSTS)


def _migu_playlist_host(host: str) -> bool:
    return _host_matches(host, _MIGU_PLAYLIST_HOSTS)


def _migu_api_host(host: str) -> bool:
    return _host_matches(host, _MIGU_API_HOSTS)


def _playlist_platform_kind(host: str) -> str:
    """Return the supported platform id for a share host, else ''."""
    if _qq_playlist_host(host):
        return "qq"
    if _netease_playlist_host(host):
        return "netease"
    if _kugou_playlist_host(host):
        return "kugou"
    if _kuwo_playlist_host(host):
        return "kuwo"
    if _migu_playlist_host(host):
        return "migu"
    return ""


def _extract_playlist_url(text: str) -> str:
    """Return the first URL in a share message, preferring a platform link.

    QQ Music's mobile share sheet copies a sentence, not a bare URL.  M3U
    links may also arrive with surrounding text, so both paths use this.
    """
    urls = _PLAYLIST_URL_RE.findall(text or "")
    if not urls:
        return ""
    for candidate in urls:
        host = urllib.parse.urlparse(candidate).hostname or ""
        if _playlist_platform_kind(host):
            return candidate.rstrip(".,;:!?)]}>\"'，。！？、；：）】》")
    return urls[0].rstrip(".,;:!?)]}>\"'，。！？、；：）】》")


def _playlist_query(url: str) -> tuple[urllib.parse.ParseResult, dict]:
    parsed = urllib.parse.urlparse((url or "").strip())
    query = dict(urllib.parse.parse_qs(
        parsed.query, keep_blank_values=False))
    fragment = parsed.fragment or ""
    if "?" in fragment:
        query.update(urllib.parse.parse_qs(
            fragment.split("?", 1)[1], keep_blank_values=False))
    return parsed, query


def _playlist_numeric_query_id(query: dict,
                               keys: tuple[str, ...]) -> str:
    for key in keys:
        for value in query.get(key, []):
            value = str(value).strip()
            if value.isdigit() and len(value) >= 3:
                return value
    return ""


def _netease_playlist_id_in_url(url: str) -> str:
    parsed, query = _playlist_query(url)
    playlist_id = _playlist_numeric_query_id(
        query, ("id", "playlistId", "playlist_id"))
    if playlist_id:
        return playlist_id
    match = re.search(r"/playlist(?:/detail)?/(\d{3,})",
                      parsed.path, re.IGNORECASE)
    return match.group(1) if match else ""


def _kugou_playlist_id_in_url(url: str) -> str:
    parsed, query = _playlist_query(url)
    if re.search(r"(?:special|plist|playlist|share)|\d{3,}",
                 parsed.path, re.IGNORECASE):
        playlist_id = _playlist_numeric_query_id(
            query, ("id", "specialid", "specialId"))
        if playlist_id:
            return playlist_id
    playlist_id = _playlist_numeric_query_id(
        query, ("specialid", "specialId"))
    if playlist_id:
        return playlist_id
    match = re.search(
        r"/(?:special/single|plist/list)/(\d{3,})",
        parsed.path, re.IGNORECASE)
    return match.group(1) if match else ""


def _kugou_global_id_in_url(url: str) -> str:
    _parsed, query = _playlist_query(url)
    for key in ("global_collection_id", "global_specialid"):
        for value in query.get(key, []):
            value = str(value).strip()
            if value.startswith("collection_"):
                return value
    return ""


def _kuwo_playlist_id_in_url(url: str) -> str:
    parsed, query = _playlist_query(url)
    playlist_id = _playlist_numeric_query_id(
        query, ("pid", "id", "playlistId"))
    if playlist_id:
        return playlist_id
    match = re.search(r"/(?:playlist_detail|playlist)/(\d{3,})",
                      parsed.path, re.IGNORECASE)
    return match.group(1) if match else ""


def _migu_playlist_id_in_url(url: str) -> str:
    parsed, query = _playlist_query(url)
    playlist_id = _playlist_numeric_query_id(
        query, ("playlistId", "id", "pid"))
    if playlist_id:
        return playlist_id
    match = re.search(r"/playlist/(\d{3,})", parsed.path, re.IGNORECASE)
    if match:
        return match.group(1)
    segment = parsed.path.rstrip("/").split("/")[-1]
    if segment.isdigit() and len(segment) >= 3:
        return segment
    return ""


def _qq_playlist_id_in_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url or "")
    query = {key.lower(): values
             for key, values in urllib.parse.parse_qs(parsed.query).items()}
    id_keys = ("disstid", "playlistid", "playlist_id")
    if re.search(r"(?:taoge|playlist|share)", parsed.path, re.IGNORECASE):
        id_keys = ("id",) + id_keys
    for key in id_keys:
        for value in query.get(key, []):
            value = str(value).strip()
            if value.isdigit() and len(value) >= 5:
                return value
    match = re.search(
        r"/(?:playlist|playlistdetail|taoge)/(\d{5,})(?:/|$)",
        parsed.path, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _qq_request_once(url: str, *, headers: dict,
                     timeout: float = 10.0,
                     max_bytes: int = 2 * 1024 * 1024
                     ) -> tuple[int, str | None, bytes]:
    """One pinned request to an official QQ Music host."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("qq-playlist-host")
    if not _qq_playlist_host(parsed.hostname):
        raise ValueError("qq-playlist-host")
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    pinned_addresses = _playlist_public_addresses(host)
    if not pinned_addresses:
        raise ValueError("qq-playlist-host")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    last_error = None
    for address, _family in pinned_addresses:
        try:
            return _playlist_request_once(
                parsed.scheme, host, port, path, timeout, address,
                max_bytes, headers=headers)
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("qq-playlist-host")


def _qq_follow(url: str, *, headers: dict, max_bytes: int = 2 * 1024 * 1024,
               max_redirects: int = 5) -> tuple[str, bytes]:
    """Follow QQ-host-only redirects and return the final URL and body."""
    current = (url or "").strip()
    seen = set()
    for _ in range(max_redirects + 1):
        if current in seen:
            raise ValueError("qq-playlist-id")
        seen.add(current)
        status, location, data = _qq_request_once(
            current, headers=headers, max_bytes=max_bytes)
        if status in (301, 302, 303, 307, 308):
            if not location:
                raise ValueError("qq-playlist-id")
            current = urllib.parse.urljoin(current, location)
            continue
        if status != 200:
            raise ValueError("qq-playlist-api")
        if len(data) > max_bytes:
            raise ValueError("playlist-too-large")
        return current, data
    raise ValueError("qq-playlist-api")


def _qq_playlist_id_from_url(url: str) -> str:
    """Extract a playlist id, resolving c6.y.qq.com short shares if needed."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if not _qq_playlist_host(parsed.hostname):
        raise ValueError("qq-playlist-host")
    playlist_id = _qq_playlist_id_in_url(url)
    if playlist_id:
        return playlist_id
    final_url, _ = _qq_follow(
        url,
        headers={"Accept": "text/html,application/xhtml+xml,*/*",
                 "Referer": "https://y.qq.com/"},
        max_bytes=256 * 1024)
    playlist_id = _qq_playlist_id_in_url(final_url)
    if playlist_id:
        return playlist_id
    raise ValueError("qq-playlist-id")


def _parse_qq_playlist_payload(payload) -> list[dict]:
    """Map QQ Music's public playlist JSON to the local track contract."""
    if not isinstance(payload, dict):
        raise ValueError("qq-playlist-api")
    code = payload.get("code")
    subcode = payload.get("subcode")
    if str(code) != "0" or (subcode is not None and str(subcode) != "0"):
        raise ValueError("qq-playlist-api")
    cdlist = payload.get("cdlist") or []
    if not cdlist or not isinstance(cdlist[0], dict):
        raise ValueError("qq-playlist-empty")
    playlist = cdlist[0]
    songs = playlist.get("songlist") or []
    if not isinstance(songs, list):
        raise ValueError("qq-playlist-api")
    try:
        total = int(playlist.get("total_song_num") or 0)
    except (TypeError, ValueError):
        total = 0
    if total > _MAX_PLAYLIST_TRACKS:
        raise ValueError("playlist-too-many-tracks")
    tracks = []
    seen = set()
    for index, song in enumerate(songs):
        if not isinstance(song, dict):
            continue
        title = str(song.get("songname") or song.get("title") or "").strip()
        if not title:
            continue
        artist = " / ".join(
            str(singer.get("name") or "").strip()
            for singer in (song.get("singer") or [])
            if isinstance(singer, dict) and str(singer.get("name") or "").strip())
        try:
            duration = max(0.0, float(song.get("interval") or 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        key = (title.casefold(), artist.casefold())
        if key in seen:
            continue
        seen.add(key)
        songmid = str(song.get("songmid") or "").strip()
        tracks.append({
            "title": title,
            "artist": artist,
            "duration": duration,
            "album": str(song.get("albumname") or "").strip(),
            "source": "qqmusic:%s" % (songmid or "%s:%d" % (
                playlist.get("disstid") or "", index)),
        })
    if not tracks:
        raise ValueError("qq-playlist-empty")
    return tracks


def _fetch_qq_playlist_tracks(url: str) -> list[dict]:
    """Read a public QQ Music playlist's metadata; never fetch audio."""
    playlist_id = _qq_playlist_id_from_url(url)
    api = (
        "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg?"
        "type=1&json=1&utf8=1&onlysong=0&disstid=%s&format=json&g_tk=5381&"
        "loginUin=0&hostUin=0&inCharset=utf8&outCharset=utf-8&notice=0&"
        "platform=yqq.json&needNewCode=0"
    ) % urllib.parse.quote(playlist_id, safe="")
    _, data = _qq_follow(
        api,
        headers={"Accept": "application/json,text/plain,*/*",
                 "Referer": "https://y.qq.com/"},
    )
    try:
        payload = json.loads(_decode_playlist(data))
    except (TypeError, ValueError):
        raise ValueError("qq-playlist-api")
    return _parse_qq_playlist_payload(payload)


def _platform_request_once(url: str, *, host_check, headers: dict,
                           timeout: float = 10.0,
                           max_bytes: int = 2 * 1024 * 1024
                           ) -> tuple[int, str | None, bytes]:
    """One pinned request to an allowlisted music-platform host."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("platform-playlist-host")
    if not host_check(parsed.hostname):
        raise ValueError("platform-playlist-host")
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    pinned_addresses = _playlist_public_addresses(host)
    if not pinned_addresses:
        raise ValueError("platform-playlist-host")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    last_error = None
    for address, _family in pinned_addresses:
        try:
            return _playlist_request_once(
                parsed.scheme, host, port, path, timeout, address,
                max_bytes, headers=headers)
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
    if last_error is not None:
        raise ValueError("platform-playlist-api") from last_error
    raise ValueError("platform-playlist-host")


def _platform_follow(url: str, *, host_check, headers: dict,
                     max_bytes: int = 2 * 1024 * 1024,
                     max_redirects: int = 5) -> tuple[str, bytes]:
    """Follow redirects only inside one platform's host allowlist."""
    current = (url or "").strip()
    seen = set()
    for _ in range(max_redirects + 1):
        if current in seen:
            raise ValueError("platform-playlist-api")
        seen.add(current)
        status, location, data = _platform_request_once(
            current, host_check=host_check, headers=headers,
            max_bytes=max_bytes)
        if status in (301, 302, 303, 307, 308):
            if not location:
                raise ValueError("platform-playlist-api")
            current = urllib.parse.urljoin(current, location)
            continue
        if status != 200:
            raise ValueError("platform-playlist-api")
        if len(data) > max_bytes:
            raise ValueError("playlist-too-large")
        return current, data
    raise ValueError("platform-playlist-api")


def _platform_playlist_id_from_url(
        url: str, *, host_check, id_func, headers: dict,
        patterns: tuple[str, ...] = (),
        max_bytes: int = 512 * 1024) -> str:
    """Extract an id, following share redirects inside the platform."""
    parsed = urllib.parse.urlparse((url or "").strip())
    if not host_check(parsed.hostname):
        raise ValueError("platform-playlist-host")
    playlist_id = id_func(url)
    if playlist_id:
        return playlist_id
    final_url, data = _platform_follow(
        url, host_check=host_check, headers=headers, max_bytes=max_bytes)
    playlist_id = id_func(final_url)
    if playlist_id:
        return playlist_id
    text = _decode_playlist(data)
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    raise ValueError("platform-playlist-id")


def _parse_netease_playlist_payload(payload) -> list[dict]:
    """Map NetEase Cloud Music's public playlist JSON to local tracks."""
    if not isinstance(payload, dict) or str(payload.get("code")) != "200":
        raise ValueError("platform-playlist-api")
    playlist = payload.get("playlist")
    if not isinstance(playlist, dict):
        raise ValueError("platform-playlist-api")
    try:
        total = int(playlist.get("trackCount") or 0)
    except (TypeError, ValueError):
        total = 0
    if total > _MAX_PLAYLIST_TRACKS:
        raise ValueError("playlist-too-many-tracks")
    songs = playlist.get("tracks") or []
    if not isinstance(songs, list):
        raise ValueError("platform-playlist-api")
    tracks = []
    seen = set()
    for song in songs:
        if not isinstance(song, dict):
            continue
        title = str(song.get("name") or "").strip()
        if not title:
            continue
        artists = song.get("ar") or song.get("artists") or []
        artist = " / ".join(
            str(item.get("name") or "").strip()
            for item in artists
            if isinstance(item, dict) and str(item.get("name") or "").strip())
        album = song.get("al") or song.get("album") or {}
        album_name = str(
            album.get("name") if isinstance(album, dict) else "").strip()
        raw_duration = song.get("dt")
        if raw_duration is None:
            raw_duration = song.get("duration") or 0
        try:
            duration = max(0.0, float(raw_duration) / 1000.0)
        except (TypeError, ValueError):
            duration = 0.0
        key = (title.casefold(), artist.casefold())
        if key in seen:
            continue
        seen.add(key)
        tracks.append({
            "title": title,
            "artist": artist,
            "duration": duration,
            "album": album_name,
            "source": "netease:%s" % (song.get("id") or ""),
        })
    if not tracks:
        raise ValueError("platform-playlist-empty")
    return tracks


def _fetch_netease_playlist_tracks(url: str) -> list[dict]:
    """Read a public NetEase playlist's metadata; never fetch audio."""
    headers = {"Accept": "application/json,text/html,*/*",
               "Referer": "https://music.163.com/"}
    playlist_id = _platform_playlist_id_from_url(
        url, host_check=_netease_playlist_host,
        id_func=_netease_playlist_id_in_url, headers=headers,
        patterns=(r"[?&]id=(\d{3,})",
                  r"playlistId[\"']?\s*[:=]\s*[\"']?(\d{3,})"))
    api = (
        "https://music.163.com/api/v6/playlist/detail?id=%s&n=1000"
        % urllib.parse.quote(playlist_id, safe="")
    )
    _, data = _platform_follow(
        api, host_check=_netease_playlist_host,
        headers={"Accept": "application/json,text/plain,*/*",
                 "Referer": "https://music.163.com/"},
        max_bytes=6 * 1024 * 1024)
    try:
        payload = json.loads(_decode_playlist(data))
    except (TypeError, ValueError):
        raise ValueError("platform-playlist-api")
    return _parse_netease_playlist_payload(payload)


def _kugou_signature(params: dict) -> str:
    """Kugou Android query signature.

    Scheme documented by MakcRe/KuGouMusicApi (MIT):
    MD5(salt + sorted key=value pairs + body + salt).
    """
    parts = []
    for key in sorted(params):
        value = params[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False,
                               separators=(",", ":"))
        parts.append("%s=%s" % (key, value))
    body = "".join(parts)
    return hashlib.md5(
        (_KUGOU_SIGN_SALT + body + _KUGOU_SIGN_SALT).encode("utf-8")
    ).hexdigest()


def _kugou_api_payload(params: dict) -> dict:
    query = {
        "area_code": 1,
        "plat": 1,
        "type": 1,
        "mode": 1,
        "personal_switch": 1,
        "extend_fields": "abtags,hot_cmt,popularization",
        "pagesize": 100,
        "dfid": "-",
        "uuid": "-",
        "appid": _KUGOU_APP_ID,
        "clientver": _KUGOU_CLIENT_VERSION,
        "clienttime": int(time.time()),
        "mid": _KUGOU_MID,
    }
    query.update(params)
    query["signature"] = _kugou_signature(query)
    api = (
        "https://gateway.kugou.com/pubsongs/v2/"
        "get_other_list_file_nofilt?"
        + urllib.parse.urlencode(query)
    )
    _, data = _platform_follow(
        api, host_check=_kugou_playlist_host,
        headers={
            "Accept": "application/json",
            "User-Agent": _KUGOU_ANDROID_UA,
            "dfid": "-",
            "clienttime": str(query["clienttime"]),
            "mid": _KUGOU_MID,
            "kg-rc": "1",
            "kg-thash": "5d816a0",
            "kg-rec": "1",
            "kg-rf": "B9EDA08A64250DEFFBCADDEE00F8F25F",
        },
        max_bytes=6 * 1024 * 1024)
    try:
        payload = json.loads(_decode_playlist(data))
    except (TypeError, ValueError):
        raise ValueError("platform-playlist-api")
    if int(payload.get("error_code") or 0) != 0:
        raise ValueError("platform-playlist-api")
    return payload


def _kugou_playlist_global_id(url: str) -> str:
    global_id = _kugou_global_id_in_url(url)
    if global_id:
        return global_id
    headers = {"Accept": "application/json,text/html,*/*",
               "Referer": "https://m.kugou.com/",
               "User-Agent": _KUGOU_MOBILE_UA}
    special_id = _platform_playlist_id_from_url(
        url, host_check=_kugou_playlist_host,
        id_func=_kugou_playlist_id_in_url, headers=headers,
        patterns=(r'"specialid"\s*:\s*"?(\d{3,})',
                  r"specialid\s*[:=]\s*['\"]?(\d{3,})"),
        max_bytes=1024 * 1024)
    api = ("https://m.kugou.com/plist/list/%s?json=true"
           % urllib.parse.quote(special_id, safe=""))
    _, data = _platform_follow(
        api, host_check=_kugou_playlist_host, headers=headers,
        max_bytes=1024 * 1024)
    try:
        payload = json.loads(_decode_playlist(data))
        info = (payload.get("info") or {}).get("list") or {}
        global_id = (info.get("global_specialid")
                     or info.get("global_collection_id"))
    except (AttributeError, TypeError, ValueError):
        global_id = ""
    if not global_id:
        raise ValueError("platform-playlist-id")
    return str(global_id)


def _fetch_kugou_playlist_tracks(url: str) -> list[dict]:
    """Read a public Kugou playlist's metadata; never fetch audio."""
    global_id = _kugou_playlist_global_id(url)
    tracks = []
    seen = set()
    begin = 0
    while begin < _MAX_PLAYLIST_TRACKS:
        payload = _kugou_api_payload({
            "begin_idx": begin,
            "global_collection_id": global_id,
        })
        block = payload.get("data") or {}
        try:
            total = int(block.get("count") or 0)
        except (TypeError, ValueError):
            total = 0
        if total > _MAX_PLAYLIST_TRACKS:
            raise ValueError("playlist-too-many-tracks")
        songs = block.get("songs") or []
        if not isinstance(songs, list) or not songs:
            break
        for song in songs:
            if not isinstance(song, dict):
                continue
            name = str(song.get("name") or "").strip()
            title = name
            if " - " in name:
                title = name.split(" - ", 1)[1].strip()
            if not title:
                title = str(song.get("filename") or "").strip()
            if not title:
                continue
            artist = " / ".join(
                str(item.get("name") or "").strip()
                for item in (song.get("singerinfo") or [])
                if isinstance(item, dict)
                and str(item.get("name") or "").strip())
            if not artist and " - " in name:
                artist = name.split(" - ", 1)[0].strip()
            album = song.get("albuminfo") or {}
            album_name = str(
                album.get("name") if isinstance(album, dict) else "").strip()
            raw_duration = (song.get("timelen")
                            or song.get("timelength") or 0)
            try:
                duration = max(0.0, float(raw_duration) / 1000.0)
            except (TypeError, ValueError):
                duration = 0.0
            key = (title.casefold(), artist.casefold())
            if key in seen:
                continue
            seen.add(key)
            tracks.append({
                "title": title,
                "artist": artist,
                "duration": duration,
                "album": album_name,
                "source": "kugou:%s" % (
                    song.get("hash") or song.get("audio_id") or ""),
            })
        begin += len(songs)
        if total and len(tracks) >= total:
            break
        if len(songs) < 100:
            break
    if not tracks:
        raise ValueError("platform-playlist-empty")
    return tracks


def _fetch_kuwo_playlist_tracks(url: str) -> list[dict]:
    """Read a public Kuwo playlist's metadata; never fetch audio."""
    headers = {"Accept": "application/json,text/html,*/*",
               "Referer": "https://www.kuwo.cn/"}
    playlist_id = _platform_playlist_id_from_url(
        url, host_check=_kuwo_playlist_host,
        id_func=_kuwo_playlist_id_in_url, headers=headers,
        patterns=(r"playlist_detail/(\d{3,})",
                  r"[\"']id[\"']\s*:\s*(\d{3,})"))
    tracks = []
    seen = set()
    total = 0
    page = 1
    while page <= 10:
        api = (
            "https://m.kuwo.cn/newh5app/wapi/api/www/playlist/"
            "playListInfo?pid=%s&pn=%d&rn=100"
            % (urllib.parse.quote(playlist_id, safe=""), page)
        )
        _, data = _platform_follow(
            api, host_check=_kuwo_playlist_host,
            headers={"Accept": "application/json",
                     "Referer": "https://m.kuwo.cn/newh5app/"
                                "playlist_detail/%s" % playlist_id},
            max_bytes=4 * 1024 * 1024)
        try:
            payload = json.loads(_decode_playlist(data))
        except (TypeError, ValueError):
            raise ValueError("platform-playlist-api")
        if str(payload.get("code")) != "200":
            raise ValueError("platform-playlist-api")
        block = payload.get("data") or {}
        try:
            total = int(block.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        if total > _MAX_PLAYLIST_TRACKS:
            raise ValueError("playlist-too-many-tracks")
        songs = block.get("musicList") or []
        if not isinstance(songs, list) or not songs:
            break
        for song in songs:
            if not isinstance(song, dict):
                continue
            title = str(song.get("name") or "").strip()
            if not title:
                continue
            artist = str(song.get("artist") or "").strip()
            try:
                duration = max(0.0, float(song.get("duration") or 0.0))
            except (TypeError, ValueError):
                duration = 0.0
            key = (title.casefold(), artist.casefold())
            if key in seen:
                continue
            seen.add(key)
            tracks.append({
                "title": title,
                "artist": artist,
                "duration": duration,
                "album": str(song.get("album") or "").strip(),
                "source": "kuwo:%s" % (song.get("musicrid") or ""),
            })
        if total and len(tracks) >= total:
            break
        page += 1
    if not tracks:
        raise ValueError("platform-playlist-empty")
    return tracks


def _fetch_migu_playlist_tracks(url: str) -> list[dict]:
    """Read a public Migu playlist's metadata; never fetch audio."""
    headers = {"Accept": "application/json,text/html,*/*",
               "Referer": "https://music.migu.cn/"}
    playlist_id = _platform_playlist_id_from_url(
        url, host_check=_migu_playlist_host,
        id_func=_migu_playlist_id_in_url, headers=headers,
        patterns=(r"playlist/(\d{3,})",
                  r"playlistId[\"']?\s*[:=]\s*[\"']?(\d{3,})"))
    tracks = []
    seen = set()
    total = 0
    page = 1
    while page <= 20:
        api = (
            "https://app.c.nf.migu.cn/MIGUM3.0/resource/playlist/"
            "song/v2.0?pageNo=%d&pageSize=50&playlistId=%s"
            % (page, urllib.parse.quote(playlist_id, safe=""))
        )
        _, data = _platform_follow(
            api, host_check=_migu_api_host,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://h5.nf.migu.cn",
                "Referer": "https://h5.nf.migu.cn/",
                "ua": "Android_migu",
                "version": "6.8.8",
                "channel": "014021I",
                "subchannel": "014021I",
            },
            max_bytes=4 * 1024 * 1024)
        try:
            payload = json.loads(_decode_playlist(data))
        except (TypeError, ValueError):
            raise ValueError("platform-playlist-api")
        if str(payload.get("code")) != "000000":
            raise ValueError("platform-playlist-api")
        block = payload.get("data") or {}
        try:
            total = int(block.get("totalCount") or 0)
        except (TypeError, ValueError):
            total = 0
        if total > _MAX_PLAYLIST_TRACKS:
            raise ValueError("playlist-too-many-tracks")
        songs = block.get("songList") or []
        if not isinstance(songs, list) or not songs:
            break
        for song in songs:
            if not isinstance(song, dict):
                continue
            title = str(song.get("songName") or "").strip()
            if not title:
                continue
            artist = " / ".join(
                str(item.get("name") or "").strip()
                for item in (song.get("singerList") or [])
                if isinstance(item, dict)
                and str(item.get("name") or "").strip())
            try:
                duration = max(0.0, float(song.get("duration") or 0.0))
            except (TypeError, ValueError):
                duration = 0.0
            key = (title.casefold(), artist.casefold())
            if key in seen:
                continue
            seen.add(key)
            tracks.append({
                "title": title,
                "artist": artist,
                "duration": duration,
                "album": str(song.get("album") or "").strip(),
                "source": "migu:%s" % (song.get("contentId") or ""),
            })
        if total and len(tracks) >= total:
            break
        page += 1
    if not tracks:
        raise ValueError("platform-playlist-empty")
    return tracks


def _load_playlist_tracks(url: str) -> list[dict]:
    """Dispatch a URL to a supported platform adapter or the M3U parser."""
    host = urllib.parse.urlparse((url or "").strip()).hostname or ""
    kind = _playlist_platform_kind(host)
    if kind == "qq":
        return _fetch_qq_playlist_tracks(url)
    if kind == "netease":
        return _fetch_netease_playlist_tracks(url)
    if kind == "kugou":
        return _fetch_kugou_playlist_tracks(url)
    if kind == "kuwo":
        return _fetch_kuwo_playlist_tracks(url)
    if kind == "migu":
        return _fetch_migu_playlist_tracks(url)
    data = _fetch_playlist_bytes(url)
    return _parse_m3u(_decode_playlist(data))


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
        result = None
        last_error = None
        for address, _family in pinned_addresses:
            try:
                result = _playlist_request_once(
                    parsed.scheme, host, port, path, timeout, address, max_bytes)
                break
            except (OSError, http.client.HTTPException) as exc:
                last_error = exc
        if result is None:
            if last_error is not None:
                raise last_error
            raise ValueError("private-playlist-host")
        status, location, data = result
        if status in (301, 302, 303, 307, 308):
            if not location:
                raise ValueError("playlist-redirect-missing")
            current = urllib.parse.urljoin(current, location)
            continue
        if status != 200:
            raise ValueError("playlist-http-error")
        if len(data) > max_bytes:
            raise ValueError("playlist-too-large")
        return data
    raise ValueError("playlist-too-many-redirects")


def _playlist_request_once(scheme: str, host: str, port: int, path: str,
                           timeout: float, pinned_ip: str,
                           max_bytes: int,
                           headers: dict | None = None
                           ) -> tuple[int, str | None, bytes]:
    """Open one pinned connection and return (status, location, body)."""
    if scheme == "https":
        connection = _PinnedHTTPSConnection(
            host, port, timeout=timeout, context=ssl.create_default_context())
    else:
        connection = _PinnedHTTPConnection(host, port, timeout=timeout)
    connection.pinned_ip = pinned_ip
    try:
        request_headers = {
            "User-Agent": "Desktop-sing-playlist/1.0",
            "Accept": "audio/x-mpegurl,application/x-mpegurl,text/plain,*/*",
        }
        if headers:
            request_headers.update(headers)
        connection.request("GET", path, headers=request_headers)
        response = connection.getresponse()
        status = response.status
        if status in (301, 302, 303, 307, 308):
            return status, response.getheader("Location"), b""
        if status != 200:
            return status, None, b""
        return status, None, response.read(max_bytes + 1)
    finally:
        connection.close()


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
    if "qq-playlist-host" in message:
        return tr("只支持 QQ 音乐官方分享链接。")
    if "qq-playlist-id" in message:
        return tr("没有从分享内容中找到 QQ 音乐歌单 ID，请粘贴完整分享文本。")
    if "qq-playlist-empty" in message:
        return tr("这个 QQ 音乐歌单不存在、未公开或没有曲目。")
    if "qq-playlist-api" in message:
        return tr("QQ 音乐歌单读取失败，请稍后重试。")
    if "platform-playlist-host" in message:
        return tr("歌单链接跳转到了不受支持的地址，已停止读取。")
    if "platform-playlist-id" in message:
        return tr("没有从链接中找到歌单 ID，请粘贴完整的分享链接或分享文本。")
    if "platform-playlist-api" in message:
        return tr("歌单读取失败。请确认歌单已公开且网络可用，然后重试。")
    if "platform-playlist-empty" in message:
        return tr("这个歌单不存在、未公开或没有曲目。")
    if "platform-playlist-url" in message:
        return tr("这个平台链接暂不支持，目前支持 QQ 音乐 / 网易云 / 酷狗 / 酷我 / 咪咕 的公开歌单；其他平台请导出 M3U/M3U8。")
    if "private-playlist-host" in message:
        return tr("这个地址指向内网或本机，已拒绝。请使用公网 M3U/M3U8 链接。")
    if "playlist-too-large" in message:
        return tr("歌单文件超过大小限制，请导入 2MB 以内的 M3U/M3U8。")
    if "playlist-too-many-tracks" in message:
        return tr("歌单曲目超过 1000 首，请精简后再导入。")
    if "unsupported-playlist-url" in message:
        return tr("无法读取这个歌单。请使用 M3U/M3U8 或支持平台的公开歌单链接。")
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
        # 三根等宽圆头柱，不带基线：带基线时三条竖线在小尺寸下会被读成「山」。
        bar_w = w * 0.16
        for cx, top in ((0.22, 0.34), (0.42, 0.16), (0.62, 0.26)):
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(
                QRectF(x + w * cx, y + h * top,
                       bar_w, y + h * 0.80 - (y + h * top)),
                bar_w / 2.0, bar_w / 2.0)
    elif kind == "history":
        p.drawEllipse(QRectF(x + w * 0.18, y + h * 0.18, w * 0.64, h * 0.64))
        p.drawLine(QPoint(int(x + w * 0.50), int(y + h * 0.32)),
                   QPoint(int(x + w * 0.50), int(y + h * 0.52)))
        p.drawLine(QPoint(int(x + w * 0.50), int(y + h * 0.52)),
                   QPoint(int(x + w * 0.65), int(y + h * 0.62)))
    elif kind == "settings":
        # 三档推子：齿轮的辐条在 18px 下会被读成太阳，推子没有歧义。
        knob = w * 0.075
        for yy, xx in ((0.30, 0.38), (0.50, 0.64), (0.70, 0.46)):
            p.drawLine(QPointF(x + w * 0.16, y + h * yy),
                       QPointF(x + w * 0.84, y + h * yy))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(x + w * xx, y + h * yy), knob, knob)
            p.setPen(QPen(color, max(1.4, w * 0.085),
                          Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
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


def _app_icon_pixmap(size: int) -> QPixmap:
    """应用自己的品牌图标（icon.png），缺失时返回空图。

    与 lyrics_overlay.make_app_icon() 同源，但这里要的是**位图**（QLabel
    显示用），不是 QIcon。歌词覆盖层不能被 lyrics_view 在模块级 import
    （会循环），所以在运行时惰性导入 —— 此时两个模块都已加载完毕。
    """
    try:
        import lyrics_overlay as lo
        icon = lo.make_app_icon()
    except Exception:
        return QPixmap()
    if icon.isNull():
        return QPixmap()
    return icon.pixmap(size, size)


def _icon(kind: str, color: str = INK, size: int = 18) -> QIcon:
    # 2x 位图交给 Qt 自己缩：声明 devicePixelRatio(2) 后 QIcon.paint 只取到
    # 左上角一块，播放/上一首的图形会被裁掉半个（2.0.13 实测）。
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
        self.setMinimumHeight(40)
        self.setObjectName("nav")

    def set_theme(self, theme):
        self._icon_color = theme.text_muted
        self._icon_color_checked = theme.text
        self._update_icon()

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
        # 三点手柄在浅色下用半透明墨点，别做成三颗黑芝麻
        dot = _tc(theme.text_muted)
        dot.setAlpha(120 if theme.appearance == "light" else 96)
        self._dot = dot
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._dot)
        for x, y in ((11, 5), (5, 11), (11, 11)):
            p.drawEllipse(QPointF(x, y), 1.3, 1.3)
        p.end()


class TitleBar(QWidget):
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    report_requested = Signal()
    settings_requested = Signal()
    mini_requested = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._stats = {}
        self._drag = None
        self._theme = None
        self.setFixedHeight(52)
        self.setObjectName("titlebar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 6, 14, 6)
        lay.setSpacing(8)
        # 左上角固定是「应用身份」：自己的图标 + 应用名，永远显示，不随页面
        # 切换而变（2026-11-28 用户要求）。页面名降级成后面一条弱化的 crumb，
        # 只作辅助信息，不再占据左上角。
        self.app_icon = QLabel()
        self.app_icon.setObjectName("appicon")
        self.app_icon.setFixedSize(22, 22)
        self.app_icon.setAlignment(Qt.AlignCenter)
        self._apply_app_icon()
        lay.addWidget(self.app_icon)
        self.app_name = QLabel(tr("桌面歌词"))
        self.app_name.setObjectName("appname")
        lay.addWidget(self.app_name)
        self.app_tag = QLabel("DESKTOP PLAYER")
        self.app_tag.setObjectName("apptag")
        lay.addWidget(self.app_tag)
        self.page_label = QLabel(tr("正在播放"))
        self.page_label.setObjectName("pagecrumb")
        lay.addWidget(self.page_label)
        lay.addStretch(1)

        self.quick_buttons = {}

        b = ui_glass.GlassButton(tr("迷你模式"), variant=ui_glass.GLASS)
        b.setObjectName("quick")
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(_icon("mini", self._quick_color(), 16))
        b.setIconSize(QSize(16, 16))
        b.clicked.connect(self.mini_requested.emit)
        lay.addWidget(b)
        self.quick_buttons["mini"] = b

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
        b = ui_glass.GlassButton(variant=ui_glass.GHOST)
        b.setObjectName("winclose" if kind == "close" else "winbtn")
        b.setFixedSize(34, 28)
        b.setCursor(Qt.PointingHandCursor)
        b.setProperty("glyph", kind)
        label = {"min": "最小化", "max": "最大化", "close": "关闭"}.get(kind, kind)
        b.setToolTip(self._tr(label))
        b.setAccessibleName(self._tr(label))
        return b

    def _quick_color(self) -> str:
        return self._theme.text_secondary if self._theme is not None else "#4F4B44"

    def _apply_app_icon(self):
        """把应用自己的品牌图标（icon.png）放进左上角的小方块。

        22px 是极限了：icon.png 里带 wordmark，缩到 18px 以下文字会糊成
        一团（实测）。所以这里保持 22px，并让方块本身跟着主题走。
        """
        pm = _app_icon_pixmap(22)
        if pm.isNull():
            # 拿不到 icon.png 时不要留一个空白方块，直接隐藏
            self.app_icon.hide()
            return
        self.app_icon.setPixmap(pm)
        self.app_icon.show()

    def set_theme(self, theme):
        self._theme = theme
        # 迷你模式按钮和窗口按钮一样必须跟着主题走：它默认是深色调色板
        # (文字 #F3F0E9)，浅色玻璃底 rgba(255,255,255,.72) 上就是白上白。
        self.quick_buttons["mini"].set_theme(theme)
        self.quick_buttons["mini"].setIcon(
            _icon("mini", self._quick_color(), 16))
        self.quick_buttons["mini"].update()
        for b in (self.b_min, self.b_max, self.b_close):
            b.set_theme(theme)
            b.update()

    def retranslate(self):
        self.app_name.setText(self._tr("桌面歌词"))
        self.page_label.setText(self._tr("正在播放"))
        self.quick_buttons["mini"].setText(self._tr("迷你模式"))
        self._win_button_labels()

    def _win_button_labels(self):
        labels = {"min": "最小化", "max": "最大化", "close": "关闭"}
        for kind, button in (("min", self.b_min), ("max", self.b_max),
                             ("close", self.b_close)):
            button.setToolTip(self._tr(labels[kind]))
            button.setAccessibleName(self._tr(labels[kind]))

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
        self.setFixedWidth(240)
        # iOS 26 的侧栏是一块浮起的面板，四周留出窗底、内缩 8px
        self._panel_fill = None
        self._panel_edge = None
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 22, 22)
        root.setSpacing(8)

        # 应用身份（图标 + 应用名 + 英文副标）统一放在标题栏左上角，永远
        # 显示（2026-11-28 用户要求）。侧栏这里原本还有一份品牌块，现在会
        # 和标题栏里的重复 40px —— 删掉它，侧栏从状态行开始。
        self.status = QLabel("●  " + tr("正在读取系统媒体"))
        self.status.setObjectName("sidestatus")
        root.addWidget(self.status)
        root.addSpacing(12)

        self.buttons = {}
        for key, text, icon_name in (
                ("now", tr("正在播放"), "play"),
                ("report", tr("听歌报告"), "report"),
                # ("history", tr("歌单"), "history"),
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
        self.set_active("now")

    def set_theme(self, theme):
        # 浅色侧栏用比窗底更沉的玻璃灰，深色用比窗底略亮的一层，
        # 这样不会和右侧白色卡片抢注意力。
        if theme.appearance == "light":
            fill = _tc(theme.surface_sunken)
            fill.setAlpha(206)
        else:
            fill = _tc(theme.surface_raised)
            fill.setAlpha(208)
        edge = _tc(theme.border)
        edge.setAlpha(160)
        self._panel_fill = fill
        self._panel_edge = edge
        for b in self.buttons.values():
            b.set_theme(theme)
        self.update()

    def paintEvent(self, event):
        if self._panel_fill is None:
            return super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        p.setPen(QPen(self._panel_edge, 1))
        p.setBrush(self._panel_fill)
        p.drawRoundedRect(rect, 22, 22)
        p.end()

    def retranslate(self):
        labels = {"now": "正在播放", "report": "听歌报告",
                  "settings": "桌面歌词设置"}
        for key, label in labels.items():
            button = self.buttons.get(key)
            if button is not None:
                button.setText(self._tr(label))
        self._apply_status()

    def _apply_status(self):
        self.status.setText(("●  " if self._status_live else "○  ")
                            + self._tr(self._status_key))

    def set_active(self, key: str):
        for k, b in self.buttons.items():
            b.setChecked(k == key)
            b._update_icon()

    def set_status(self, text: str, live: bool = False):
        # 60fps 心跳里每帧都调这里；文案没变就别重新 polish 样式
        # （unpolish/polish 会触发整棵控件树的样式重算）。
        if text == self._status_key and bool(live) == self._status_live:
            return
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
        self._wash_cache_key = None
        self._wash_pix = None
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_theme(self, theme):
        self._base = _tc(theme.bg)
        dark = theme.appearance != "light"
        self._dark = dark
        # Light themes keep the stage on the app palette instead of forcing a
        # deep listening surface; lyric text switches to theme colours.
        # Dark keeps the listening surface (sunken is the groove token and
        # deliberately deeper than the card now, which would flatten the stage).
        self._scrim = _tc(theme.surface if dark else theme.bg)
        self.update()

    def set_cover(self, cover):
        self.cover = cover
        self._cover_cache_key = None
        self.update()

    def set_accent(self, color):
        self.accent = QColor(color)
        self.update()

    def paintEvent(self, e):
        # 整块舞台底是一次性画好的位图：封面压暗 + 主色晕 + 顶部渐变 + 唱片
        # 纹路全是静态的。之前每帧重画三条全尺寸渐变（歌词 90ms 刷新一次，
        # 等于每秒 11 次重算整屏），是界面/动画发卡的主要来源之一。
        key = (self.width(), self.height(), round(self.devicePixelRatioF(), 2),
               self.accent.rgb(), self._base.rgb(), self._scrim.rgb(),
               self._dark,
               self.cover.cacheKey() if self.cover is not None
               and not self.cover.isNull() else 0)
        if self._wash_cache_key != key or self._wash_pix is None:
            self._wash_pix = self._render_wash()
            self._wash_cache_key = key
        QPainter(self).drawPixmap(0, 0, self._wash_pix)

    def _render_wash(self):
        dpr = max(1.0, self.devicePixelRatioF())
        w, h = max(1, self.width()), max(1, self.height())
        pix = QPixmap(int(w * dpr), int(h * dpr))
        pix.setDevicePixelRatio(dpr)
        p = QPainter(pix)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
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
            p.setOpacity(0.22 if self._dark else 0.10)
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
        alphas = (95, 120, 190) if self._dark else (40, 64, 90)
        c.setAlpha(alphas[0])
        shade.setColorAt(0.0, c)
        c.setAlpha(alphas[1])
        shade.setColorAt(0.52, c)
        c.setAlpha(alphas[2])
        shade.setColorAt(1.0, c)
        p.fillRect(0, 0, w, h, shade)
        if self._dark:
            # 2-3% 同心唱片纹：空白处的低调签名
            p.setPen(QPen(QColor(255, 255, 255, 7), 1))
            p.setBrush(Qt.NoBrush)
            cx, cy = w * 0.26, h * 0.47
            radius = 46
            limit = max(w, h) * 0.72
            while radius < limit:
                p.drawEllipse(QPointF(cx, cy), radius, radius)
                radius += 18
        p.end()
        return pix

class LyricsCanvas(QWidget):
    seek_requested = Signal(float)

    # ---- 手动滚动的时序常量 ----
    SCROLL_RETURN_DELAY = 2.4   # 停手多久后滑回当前句（秒）
    SCROLL_FOLLOW_TAU = 0.075   # 跟随/回弹的指数时间常数（秒，帧率无关）
    SCROLL_FRICTION = 0.22      # 惯性速度衰减时间常数（秒）
    SCROLL_NOTCH_UNITS = 120.0  # Windows 滚轮一格 = 120 angleDelta units
    SCROLL_MIN_VEL = 0.05       # 低于此线速度（行/秒）不再惯性滑行
    SCROLL_MAX_LINES_PER_FRAME = 0.6   # 单帧最多移动多少行（防瞬移）

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
        # 滚动模型：_focus 是「锚点上那一行的小数行号」。
        #   _follow=True  → 锚点跟着当前播放行走（听歌时的常态）
        #   _follow=False → 用户手动滚动，锚点由 _focus_target 决定
        # 用**行号**而不是像素做基准：滚动范围天然可夹（不会滚进空白），
        # 换行时的位移也连续（原来按行号重排会整块跳一格）。
        self._focus = 0.0
        self._focus_target = 0.0
        self._focus_vel = 0.0
        self._follow = True
        self._focus_snap = True       # 换歌/首帧：直接落位，不做滑动
        self._last_input_t = 0.0
        self._last_step_t = 0.0
        self._last_anim_t = 0.0
        self._reduce_motion = False
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
        self._immersive = False
        self._dark = True
        self._bg = QColor("#14171e")
        self._text = QColor(238, 239, 242)
        self._text2 = QColor(215, 218, 224)
        # 滚动动画的专用时钟：只在有动画时跑（settled 就停表），与主窗口的
        # 刷新节奏解耦 —— 主窗口在非播放页只有 90ms 一拍，靠它驱动滚动会顿。
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)
        self._anim_timer.timeout.connect(self._anim_tick)

    # ---------------- 滚动模型 ----------------

    def _anchor_ratio(self) -> float:
        """锚点在歌词区里的相对高度：普通态偏上，沉浸态居中。"""
        return 0.42 if self._immersive else 0.20

    def _focus_limits(self) -> tuple:
        """可滚动范围（焦点行号）：[0, 末行]。

        焦点 = 锚点上那一行的小数行号。夹到 [0, n-1] 保证「锚点永远落在
        一句真实的歌词上」—— 旧实现没有夹取，往上滚可以一直滚到整屏空白。
        """
        n = len(self.lines)
        if n <= 0:
            return 0.0, 0.0
        return 0.0, float(n - 1)

    def _anchor_effective(self, focus: float, h: float = None) -> float:
        """锚点实际落在内容区的哪个 y。

        锚点默认在 20%（沉浸态 42%），但歌词不够长时下方会空一大块。
        这里把锚点夹到「最后一行贴着视口底 / 第一行贴着视口顶」之间，
        于是：往歌尾滚，最后一句会停在底部；往歌头滚，第一句会停在顶部；
        中间段落保持「当前句在上方 1/5 处」的聚光灯布局。
        """
        n = len(self.lines)
        if n <= 0:
            return 0.0
        if h is None:
            h = self._content_h()
        desired = h * self._anchor_ratio()
        lower = h - (n - 1 - focus) * self._line_h   # 最后一行贴视口底
        upper = focus * self._line_h                 # 第一行贴视口顶
        if lower > upper:
            return desired        # 歌词比视口还短：居中即可
        return max(lower, min(upper, desired))

    def _content_h(self) -> float:
        if self._content_rect is not None:
            return float(self._content_rect[3])
        return float(self.height())

    def _clamp_focus(self, value: float) -> float:
        lo, hi = self._focus_limits()
        if lo > hi:
            lo, hi = hi, lo
        return max(lo, min(hi, value))

    def _ensure_anim(self):
        """有未完成的动画就把 16ms 时钟拉起来，settled 后自动停。"""
        if not self._anim_timer.isActive():
            # 表停了很久再启动时，_last_anim_t 是陈的：第一拍按固定 16ms 算，
            # 否则会按「停表时长」跳一大步（看着像瞬移）。
            self._last_anim_t = 0.0
            self._anim_timer.start()

    def _anim_tick(self, dt=None):
        """滚动动画的一拍：惯性衰减 → 弹簧追目标 → 需要时回到跟随。

        帧率无关：位移用「距上次一拍的秒数」算，不看这一帧渲染了多久。
        以前衰减写在 paintEvent 里（``self._manual *= 0.86``），高刷屏和
        60Hz 屏的回弹速度完全不一样，而且是一格一格的硬跳。

        dt 可外部传入（测试用），默认按真实时钟算。
        """
        now = time.monotonic()
        if dt is None:
            dt = 0.016
            if self._last_anim_t:
                dt = max(0.0, min(0.05, now - self._last_anim_t))
        self._last_anim_t = now

        # 1) 惯性：松手后继续滑行，速度按指数衰减（只触控板有）
        if abs(self._focus_vel) > self.SCROLL_MIN_VEL:
            self._focus_target += self._focus_vel * dt
            self._focus_vel *= pow(2.0, -dt / self.SCROLL_FRICTION)
        else:
            self._focus_vel = 0.0

        # 2) 停手够久 ⇒ 回到「跟随当前句」
        if (not self._follow and self._last_input_t
                and now - self._last_input_t > self.SCROLL_RETURN_DELAY):
            self._follow = True
            self._focus_vel = 0.0
        if self._follow:
            self._focus_target = float(max(0, self.cur_idx))

        self._focus_target = self._clamp_focus(self._focus_target)

        # 3) 弹簧逼近目标：位置连续，不跳格
        if self._reduce_motion:
            self._focus = self._focus_target
        else:
            k = 1.0 - pow(2.0, -dt / self.SCROLL_FOLLOW_TAU)
            step = (self._focus_target - self._focus) * k
            # 单帧位移上限：seek 跳很远时也不许一帧硬跳（那会看着像瞬移）
            limit = self.SCROLL_MAX_LINES_PER_FRAME
            if step > limit:
                step = limit
            elif step < -limit:
                step = -limit
            self._focus += step

        if (abs(self._focus - self._focus_target) < 0.004
                and abs(self._focus_vel) <= self.SCROLL_MIN_VEL):
            self._focus = self._focus_target
            self._focus_vel = 0.0
            self._anim_timer.stop()
        self.update()

    def set_reduce_motion(self, enabled: bool):
        """「减少动态效果」开启时：滚动直接落位，不做惯性与回弹。"""
        self._reduce_motion = bool(enabled)
        if self._reduce_motion:
            self._focus = self._focus_target
            self._focus_vel = 0.0
            self._anim_timer.stop()

    def set_content_rect(self, x, y, w, h):
        self._content_rect = (int(x), int(y), max(1, int(w)), max(1, int(h)))
        self.update()

    def set_immersive(self, on: bool):
        on = bool(on)
        if on == getattr(self, "_immersive", False):
            return
        self._immersive = on
        self._line_h = 96.0 if on else 64.0
        self.update()

    def set_theme(self, theme):
        self._dark = theme.appearance != "light"
        self._bg = _tc(theme.bg)
        self._text = _tc(theme.text)
        self._text2 = _tc(theme.text_secondary)
        self.accent = _tc(theme.accent_fill if self._dark
                             else theme.accent_text)
        self._accent_text = _tc(theme.accent_text)
        self.update()

    def _readable_accent(self, color: QColor) -> QColor:
        """Cover-derived accent must stay legible on the light stage.

        A pastel album cover can hand us #EF704D, which only reaches 2.6:1 on
        the pale pink wash — the karaoke line then reads as a ghost. Dark
        appearances keep the raw colour because a bright accent on near-black
        is already above 6:1.
        """
        if self._dark:
            base = QColor(color)
            if ui_theme.contrast_ratio(base, self._bg) >= 4.5:
                return base
            # 封面色偶有偏暗（暗红 / 深棕），直接拿来当深色高亮会比未唱行还难看清；
            # 朝白色提亮、保住色相，够 4.5:1 就停。
            for step in range(1, 13):
                t = step / 12.0
                mix = QColor(
                    int(round(base.red() * (1 - t) + 255 * t)),
                    int(round(base.green() * (1 - t) + 255 * t)),
                    int(round(base.blue() * (1 - t) + 255 * t)))
                if ui_theme.contrast_ratio(mix, self._bg) >= 4.5:
                    return mix
            return QColor("#FFFFFF")
        # 浅色不要直接把封面色一路混黑（会变成脏棕色），而是朝主题的
        # 深主色收，保住色相，够 4.5:1 就停。
        target = QColor(getattr(self, "_accent_text", "#A93618"))
        # 先从 45% 起混，别让封面色一路原样压到 4.5:1 才变成暗棕。
        for step in range(5, 13):
            t = step / 12.0
            mix = QColor(
                int(round(color.red() * (1 - t) + target.red() * t)),
                int(round(color.green() * (1 - t) + target.green() * t)),
                int(round(color.blue() * (1 - t) + target.blue() * t)))
            if ui_theme.contrast_ratio(mix, self._bg) >= 4.5:
                return mix
        return target

    def _dim_alpha(self, dist: int) -> int:
        """Opacity for a non-current lyric line.

        Dark keeps the 150→46 falloff that fades lines into the stage. Light
        needs a much higher floor: 46/255 of dark ink on a pale wash is
        ~1.5:1, i.e. invisible. The light curve stays above 3:1 for five
        lines out.
        """
        if self._dark:
            return max(46, 150 - abs(dist) * 20)
        return max(126, 148 - abs(dist) * 10)

    def _ghost_ink(self) -> QColor:
        """Un-sung part of the current line: 3:1-ish, never dimmer than the wash."""
        return self._lyric_ink(72 if self._dark else 150)

    def _trans_ink(self, alpha: int) -> QColor:
        """Translation colour for the current appearance.

        Was a hard-coded light grey (206,209,215), which is invisible on a
        light stage (1.05–1.11:1). Light now uses the secondary text token
        and never drops below 200/255.
        """
        if self._dark:
            return QColor(206, 209, 215, max(38, alpha - 60))
        color = QColor(self._text2)
        color.setAlpha(min(255, max(210, alpha + 40)))
        return color

    def _lyric_ink(self, alpha=255, secondary=False):
        if self._dark:
            color = QColor(215, 218, 224) if secondary else QColor(238, 239, 242)
        else:
            color = QColor(self._text2 if secondary else self._text)
        color.setAlpha(int(alpha))
        return color

    def set_lyrics(self, lines, trans, song=None, *, empty_message_key=None,
                   empty_description_key=None):
        self.lines = list(lines or [])
        self.trans = dict(trans or {})
        self.song = dict(song or self.song or {})
        self.cur_idx = -1
        # 换歌 ⇒ 复位滚动状态（否则新歌会继承上一首的滚动位置）
        self._focus = 0.0
        self._focus_target = 0.0
        self._focus_vel = 0.0
        self._follow = True
        self._focus_snap = True
        self.empty_message_key = empty_message_key or "等待播放"
        self.empty_description_key = (
            empty_description_key
            or "在任意接入系统媒体控制的播放器中开始播放")
        self.update()

    def set_playback(self, pos, cur_idx, playing, accent=None, cover=None,
                     song=None, font_family=""):
        self.pos = float(pos or 0.0)
        prev_idx = self.cur_idx
        self.cur_idx = int(cur_idx)
        self.playing = bool(playing)
        if accent is not None:
            self.accent = self._readable_accent(QColor(accent))
        if cover is not None:
            self.cover = cover
            self._cover_cache_key = None
        if song is not None:
            self.song = dict(song)
        if font_family and font_family != self._font_family:
            self._font_family = font_family
            self._font_cache.clear()
        # 跟随模式：锚点跟着当前行走。**用弹簧追**，不要直接赋值 ——
        # 直接赋值会让整块歌词在换行瞬间硬跳一格（原来就是这样）。
        if self._follow:
            self._focus_target = float(max(0, self.cur_idx))
            if self._focus_snap or self._reduce_motion:
                # 换歌/首帧/减少动态效果：直接落位
                self._focus = self._focus_target
                self._focus_snap = False
            elif abs(self._focus - self._focus_target) > 0.001:
                self._ensure_anim()
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
        """滚轮/触控板：手动浏览歌词。

        两条关键修正：
        1) **方向**：滚轮向上（angleDelta.y() > 0）应该往**过去**看。
           旧代码是 ``_manual -= delta``，而 _manual 是「往下加」的，
           实际把上下滚反了 —— 往下滚看到的是过去的歌词。
        2) **触控板**：精确式触控板只给 pixelDelta（angleDelta 为 0），
           旧代码只看 angleDelta，触控板在部分驱动下完全不动。两条都取，
           pixelDelta 优先（它才是高分辨率的真实位移）。

        触控板（pixelDelta）额外带惯性：松手后继续滑行再缓缓停下；
        鼠标滚轮是离散的，不给惯性，用弹簧到位即可。
        """
        if not self.lines:
            return
        pixels = e.pixelDelta().y()
        angle = e.angleDelta().y()
        if not pixels and not angle:
            return
        now = time.monotonic()
        if pixels:
            step_lines = pixels / self._line_h
        else:
            # 120 units ≈ Windows 滚轮一格；一格走 3 行歌词
            step_lines = (angle / self.SCROLL_NOTCH_UNITS) * 3.0
        # 向上滚（delta > 0）→ 往过去看 → 焦点行号变小
        self._focus_target = self._clamp_focus(self._focus_target - step_lines)
        self._follow = False
        self._last_input_t = now
        # 触控板惯性：用连续两次事件的位移/间隔估速度
        if pixels and self._last_step_t:
            dt = now - self._last_step_t
            if 0.001 < dt < 0.2:
                inst = -step_lines / dt          # 行/秒，负=往过去
                self._focus_vel = (self._focus_vel * 0.4 + inst * 0.6)
        else:
            self._focus_vel = 0.0
        self._last_step_t = now
        if self._reduce_motion:
            # 减少动态效果：直接落位，不做弹簧/惯性
            self._focus = self._focus_target
            self._focus_vel = 0.0
            self._anim_timer.stop()
        else:
            self._ensure_anim()
        e.accept()

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
        """把内容区里的 y 坐标换算成歌词行号。

        旧实现用 ``content_h * 0.20`` + cur_idx 反推，既没考虑沉浸模式
        的 0.42 锚点，也没考虑用户手动滚动后的偏移 —— 手动滚过之后
        点某一行，跳到的是**另一行**。现在和绘制共用同一套几何。
        """
        h = float(content_h) if content_h is not None else self._content_h()
        anchor_y = self._anchor_effective(self._focus, h)
        idx = int(round(self._focus + (y - anchor_y) / self._line_h))
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

        # The now-playing layout puts the active line near the upper quarter,
        # like a desktop player's lyric pane, not in the vertical centre.
        # Immersive mode is the opposite: centre the block and scale it up.
        # h 是内容区高度（不是整个控件），锚点与点选换算都用它，保证一致。
        anchor_y = self._anchor_effective(self._focus, h)
        focus = self._focus

        # 画「焦点行」上下够覆盖视口的整段歌词。旧代码固定只画
        # cur_idx-2 .. cur_idx+6 —— 用户手动滚出去以后，上下都是空白，
        # 看着像「滚不动」。
        above = anchor_y / self._line_h
        below = (h - anchor_y) / self._line_h
        first = max(0, int(focus - above) - 1)
        last = min(len(self.lines), int(focus + below) + 2)
        for i in range(first, last):
            dist = i - focus
            y = anchor_y + dist * self._line_h
            if y < -40 or y > h + 40:
                continue
            text = str(self.lines[i][1] or "")
            if not text.strip():
                continue
            current = (i == self.cur_idx)
            if current:
                self._paint_current(p, text, i, y, w)
            elif self._immersive:
                alpha = self._dim_alpha(dist)
                f = self._font(26 if abs(dist) <= 2 else 21, bold=False)
                p.setFont(f)
                p.setPen(self._lyric_ink(alpha))
                fm = QFontMetrics(f)
                p.drawText(QRectF(0, y - 22, w, 44),
                           Qt.AlignHCenter | Qt.AlignVCenter,
                           fm.elidedText(text, Qt.ElideRight, max(120, w - 80)))
                tr = self.trans.get(i, "")
                if tr and abs(dist) <= 1:
                    tf = self._font(16)
                    p.setFont(tf)
                    p.setPen(self._trans_ink(alpha))
                    fm2 = QFontMetrics(tf)
                    p.drawText(QRectF(0, y + 26, w, 24),
                               Qt.AlignHCenter | Qt.AlignVCenter,
                               fm2.elidedText(tr, Qt.ElideRight, max(120, w - 80)))
            else:
                alpha = self._dim_alpha(dist)
                f = self._font(20 if abs(dist) <= 2 else 17, bold=False)
                p.setFont(f)
                p.setPen(self._lyric_ink(alpha))
                fm = QFontMetrics(f)
                p.drawText(QRectF(24, y - 16, w - 48, 32),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(text, Qt.ElideRight, max(80, w - 48)))
                tr = self.trans.get(i, "")
                if tr and abs(dist) <= 1:
                    tf = self._font(13)
                    p.setFont(tf)
                    p.setPen(self._trans_ink(alpha))
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
        if self._immersive:
            limit = max(200.0, w - 120)
            size = 58
            while size > 30:
                fm = QFontMetrics(self._font(size, bold=True))
                if fm.horizontalAdvance(text) <= limit:
                    break
                size -= 2
            f = self._font(size, bold=True)
            fm = QFontMetrics(f)
            shown = fm.elidedText(text, Qt.ElideRight, limit)
            rect = QRectF(0, y - 46, w, 92)
            p.setFont(f)
            p.setPen(self._ghost_ink())
            p.drawText(rect, Qt.AlignCenter, shown)
            frac = self._line_fraction(idx)
            if frac > 0.0:
                txt_w = fm.horizontalAdvance(shown)
                left = max(0.0, (w - txt_w) / 2.0)
                p.save()
                p.setClipRect(QRectF(left, rect.top(), txt_w * frac, rect.height()))
                p.setPen(self.accent)
                p.drawText(rect, Qt.AlignCenter, shown)
                p.restore()
            tr = self.trans.get(idx, "")
            if tr:
                tf = self._font(18)
                p.setFont(tf)
                p.setPen(self._trans_ink(170))
                fm2 = QFontMetrics(tf)
                p.drawText(QRectF(0, y + 34, w, 26), Qt.AlignCenter,
                           fm2.elidedText(tr, Qt.ElideRight, max(120, w - 120)))
            return
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
        p.setPen(self._ghost_ink())
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
            p.setPen(self._trans_ink(170))
            fm2 = QFontMetrics(tf)
            p.drawText(self._translation_rect(y, w),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       fm2.elidedText(tr, Qt.ElideRight, max(80, w - 48)))

    def _paint_empty(self, p, w, h):
        cy = h * 0.40
        p.setPen(QPen(self._lyric_ink(30 if self._dark else 96), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(w / 2.0, cy), 30, 30)
        _draw_icon(p, "note", QRectF(w / 2.0 - 13, cy - 13, 26, 26),
                   self._lyric_ink(150 if self._dark else 200))
        p.setPen(self._lyric_ink(225))
        p.setFont(self._font(32, bold=True))
        p.drawText(QRectF(0, cy + 48, w, 46), Qt.AlignCenter,
                   self._tr(self.empty_message_key))
        p.setPen(self._trans_ink(150))
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
        self._placeholder_top = _tc(theme.surface_raised)
        self._placeholder_bottom = _tc(theme.surface_sunken)
        self._placeholder_icon = _tc(theme.text_muted)
        self._ring = _tc(theme.text)
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
        self.immersive_btn = ui_glass.GlassButton(
            tr("沉浸歌词"), variant=ui_glass.GLASS)
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
        bl.setContentsMargins(14, 18, 16, 12)
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
        self._playing = False
        self._immersive = False
        self._toggle_icon_key = None
        self._time_text = ""

    def set_immersive(self, on: bool):
        on = bool(on)
        if on == self._immersive:
            return
        self._immersive = on
        for widget in (self.hero_cover, self.source, self.track_title,
                       self.track_artist, self.bar):
            widget.setVisible(not on)
        self.canvas.set_immersive(on)
        self.immersive_btn.raise_()
        self._apply_layout()

    def _round_button(self, icon_name: str, primary: bool = False,
                      label: str = "") -> QPushButton:
        b = ui_glass.GlassButton(
            variant=ui_glass.ACCENT if primary else ui_glass.GLASS)
        b.setObjectName("playprimary" if primary else "playround")
        b.setFixedSize(46 if primary else 38, 46 if primary else 38)
        b.setCursor(Qt.PointingHandCursor)
        if label:
            b.setToolTip(self._tr(label))
            b.setAccessibleName(self._tr(label))
        color = self._on_accent_color() if primary else self._icon_color()
        b.setIcon(_icon(icon_name, color, 20 if primary else 17))
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

    def _refresh_toggle_icon(self):
        color = self._on_accent_color()
        key = (self._playing, color)
        if key == self._toggle_icon_key:
            return
        self.b_toggle.setIcon(
            _icon("pause" if self._playing else "play", color, 20))
        self._toggle_icon_key = key

    _SOURCE_TRACKING = 2

    def _fit_source_label(self):
        text = self.source.text()
        fm = self.source.fontMetrics()
        width = (fm.horizontalAdvance(text)
                 + self._SOURCE_TRACKING * max(0, len(text) - 1) + 8)
        self.source.resize(width, self.source.sizeHint().height())

    def set_theme(self, theme):
        self._theme = theme
        self.backdrop.set_theme(theme)
        self.cover.set_theme(theme)
        self.hero_cover.set_theme(theme)
        self.canvas.set_theme(theme)
        self.source.setStyleSheet("")
        self.track_title.setStyleSheet("")
        self.track_artist.setStyleSheet("")
        self.immersive_btn.set_theme(theme)
        self.immersive_btn.setIcon(_icon("expand", self._icon_color(), 15))
        self.b_prev.set_theme(theme)
        self.b_next.set_theme(theme)
        self.b_toggle.set_theme(theme)
        self.b_prev.setIcon(_icon("prev", self._icon_color(), 17))
        self._refresh_toggle_icon()
        self.b_next.setIcon(_icon("next", self._icon_color(), 17))
        # The lyric canvas is translucent: repaint it so it does not keep a
        # stale copy of the previous backdrop baked into its backing store.
        self.canvas.update()
        self.update()
        self._fit_source_label()

    def _release_seek(self):
        self._drag = False
        if self._duration > 0:
            self.seek_requested.emit(self.slider.value() / 1000.0 * self._duration)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_layout()

    def _apply_layout(self):
        self.backdrop.setGeometry(0, 0, self.width(), self.height())
        if self._immersive:
            w, h = self.width(), self.height()
            self.canvas.setGeometry(0, 0, w, h)
            pad_x = max(28, int(w * 0.05))
            pad_y = max(30, int(h * 0.07))
            self.canvas.set_content_rect(
                pad_x, pad_y, max(240, w - 2 * pad_x), max(200, h - 2 * pad_y))
            self.canvas.show()
            self.canvas.raise_()
            self.immersive_btn.adjustSize()
            self.immersive_btn.move(max(12, w - self.immersive_btn.width() - 24), 18)
            self.immersive_btn.raise_()
            return
        # The right-hand stage mirrors a full player layout: artwork on the
        # left, lyrics on the right, transport along the bottom. The lyric
        # canvas owns only the text column; it is never covered by artwork.
        if self.width() < 780:
            # Narrow layouts: give lyrics the full stage and put the artwork
            # behind the translucent lyric layer instead of squeezing the text.
            self.hero_cover.hide()
            self.source.move(24, 18)
            self._fit_source_label()
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
            bar_h = 100
            self.bar.setGeometry(20, self.height() - bar_h - 14,
                                 self.width() - 40, bar_h)
            self.slider.setGeometry(24, 8, max(80, self.bar.width() - 48), 18)
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
        self._fit_source_label()
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
        bar_h = 100
        self.bar.setGeometry(20, self.height() - bar_h - 14, self.width() - 40, bar_h)
        self.slider.setGeometry(24, 8, max(80, self.bar.width() - 48), 18)
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
        self._fit_source_label()
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
        self._playing = bool(playing)
        self._refresh_toggle_icon()
        self.b_toggle.setToolTip(self._tr("暂停") if playing else self._tr("播放"))
        cur = int(max(0, pos))
        if self._duration > 0:
            dur = int(self._duration)
            label = "%d:%02d / %d:%02d" % (cur // 60, cur % 60,
                                           dur // 60, dur % 60)
        else:
            label = "%d:%02d" % (cur // 60, cur % 60)
        # 60fps 心跳下每秒只变一次；同文案别再触发 QLabel 重排
        if label != self._time_text:
            self._time_text = label
            self.time.setText(label)

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
        self._label_px = 12
        self.setMinimumHeight(170)

    def set_theme(self, theme):
        self._line = _tc(theme.accent_fill)
        self._dot = _tc(theme.accent_fill)
        self._dot_ring = _tc(theme.surface)
        self._label = _tc(theme.text_muted)
        self._label_px = max(12, int(getattr(theme, "fs_caption", 12)))
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
        p.setFont(_pick_ui_font(self._label_px))
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
        self.panel = lo.SettingsPanel(ov, flags=Qt.Widget, embedded=True)
        self.panel.setObjectName("settingsSurface")
        self.panel.set_theme(self._current_theme())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(14)
        lay.addWidget(self.appearance)
        lay.addWidget(self.panel)
        self.appearance.refresh()

    def _current_theme(self):
        manager = getattr(self.ov, "theme_manager", None)
        if manager is not None:
            try:
                return manager.current()
            except Exception:
                pass
        getter = getattr(self.ov, "_current_theme", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                pass
        return None

    def rebuild(self):
        import lyrics_overlay as lo
        old_panel = self.panel
        self.layout().removeWidget(old_panel)
        self.panel = lo.SettingsPanel(self.ov, flags=Qt.Widget, embedded=True)
        self.panel.setObjectName("settingsSurface")
        self.panel.set_theme(self._current_theme())
        self.layout().addWidget(self.panel)
        old_panel.deleteLater()
        self.retranslate()

    def retranslate(self):
        self.appearance.retranslate()

    def set_theme(self, theme):
        # The embedded legacy panel builds its stylesheet once at construction;
        # refresh it whenever the app theme changes.
        self.appearance.refresh()
        self.panel.set_theme(theme)


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
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QVBoxLayout()
        head.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.bar = QFrame()
        self.bar.setObjectName("sectionBar")
        # iOS 分组标题没有左侧色条，只靠字号/字重分层
        self.bar.setFixedSize(0, 0)
        self.bar.hide()
        self.title = QLabel()
        self.title.setObjectName("appearanceTitle")
        row.addWidget(self.title)
        row.addStretch(1)
        head.addLayout(row)
        self.hint = QLabel()
        self.hint.setObjectName("appearanceHint")
        self.hint.setWordWrap(True)
        head.addWidget(self.hint)
        root.addLayout(head)

        seg_track = QFrame()
        seg_track.setObjectName("segTrack")
        seg_box = QHBoxLayout(seg_track)
        seg_box.setContentsMargins(3, 3, 3, 3)
        seg_box.setSpacing(3)
        self.seg_buttons = {}
        for key in self._APPEARANCES:
            b = ui_glass.GlassButton(variant=ui_glass.SEGMENT)
            b.setObjectName("appearanceSeg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(32)
            b.clicked.connect(lambda _=False, k=key: self._pick_appearance(k))
            seg_box.addWidget(b, 1)
            self.seg_buttons[key] = b
        root.addWidget(seg_track)

        swatches = QHBoxLayout()
        swatches.setSpacing(10)
        self.swatch_buttons = {}
        for theme_id in self._THEMES:
            b = _ThemeSwatchButton(theme_id, tr)
            b.clicked.connect(lambda _=False, t=theme_id: self._pick_theme(t))
            swatches.addWidget(b, 1)
            self.swatch_buttons[theme_id] = b
        root.addLayout(swatches)

        divider = QWidget()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        root.addWidget(divider)

        motion_row = QHBoxLayout()
        motion_row.setSpacing(10)
        self.motion_label = QLabel()
        self.motion_label.setObjectName("rowlabel")
        self.motion_label.setMinimumHeight(36)
        import lyrics_overlay as lo
        self.motion_switch = lo.Switch(False, w=51, h=31)
        self.motion_switch.toggled.connect(self._toggle_motion)
        motion_row.addWidget(self.motion_label)
        motion_row.addStretch(1)
        motion_row.addWidget(self.motion_switch)
        root.addLayout(motion_row)

        self.motion_hint = QLabel()
        self.motion_hint.setObjectName("appearanceHint")
        self.motion_hint.setWordWrap(True)
        root.addWidget(self.motion_hint)
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
        self.motion_switch.blockSignals(True)
        self.motion_switch.setChecked(reduce_motion)
        self.motion_switch.blockSignals(False)
        theme = manager.current() if manager is not None else None
        if theme is not None:
            self.motion_switch.set_accent(_tc(theme.accent_fill))
            self.motion_switch.set_theme(theme)
        for button in self.seg_buttons.values():
            if theme is not None:
                button.set_theme(theme)
            button.update()

    def retranslate(self):
        tr = self._tr
        self.title.setText(tr("应用主题"))
        self.hint.setText(tr("选择应用配色；跟随系统会随 Windows 深浅色切换"))
        for key, label in (("system", "跟随系统"), ("light", "浅色"),
                           ("dark", "深色")):
            self.seg_buttons[key].setText(tr(label))
        for button in self.swatch_buttons.values():
            button.retranslate()
        self.motion_label.setText(tr("减少动态效果"))
        self.motion_hint.setText(tr("关闭页面淡入和过渡动画"))
        self.motion_label.setAccessibleName(tr("减少动态效果"))
        self.motion_switch.setToolTip(tr("关闭页面淡入和过渡动画"))
        self.motion_switch.setAccessibleName(tr("减少动态效果"))


class _ThemePreview(QWidget):
    """Mini player mock: one cover block + one accent lyric line.

    2026-11-28 重做：旧版画了顶栏分割线、侧栏分割线、双层描边封面、
    三条歌词横线，十几根 1px 线条挤在 148x64 里 —— 用户反馈「线框看着
    很杂乱」。现在只用**圆角色块**表达结构（底色 / 侧栏 / 封面 / 主色
    歌词 / 次级歌词），一条描边都不画（只有最外框），靠明度层次而不是
    线框来区分区块。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(148, 64)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._theme = None

    def set_theme(self, theme):
        self._theme = theme
        self.update()

    def paintEvent(self, _event):
        theme = self._theme
        if theme is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        radius = 10.0
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.setClipPath(path)
        p.fillRect(rect, _tc(theme.bg))

        # 侧栏：只是一块更沉的底色，不再画分隔线
        side = max(26.0, w * 0.22)
        p.fillRect(QRectF(0, 0, side, h), _tc(theme.surface))

        # 舞台：铺一层极淡的主色，让每套主题的性格能一眼看出来
        stage = QRectF(side, 0, w - side, h)
        tint = _tc(theme.accent_fill)
        tint.setAlpha(40 if theme.appearance == "dark" else 22)
        p.setPen(Qt.NoPen)
        p.fillRect(stage, tint)

        # 侧栏内容：品牌点 + 一条高亮项，其余留白
        p.setBrush(_tc(theme.accent_fill))
        p.drawRoundedRect(QRectF(7, 9, 7, 7), 2.5, 2.5)
        p.setBrush(_tc(theme.text_muted))
        p.drawRoundedRect(QRectF(8, h - 13, side - 16, 3), 1.5, 1.5)

        # 舞台：封面 + 当前句（主色）+ 一行次级歌词
        size = min(30.0, h - 20.0)
        cover = QRectF(side + (w - side - size) / 2.0 - 34.0,
                       (h - size) / 2.0, size, size)
        p.setBrush(_tc(theme.accent_fill))
        p.drawRoundedRect(cover, size * 0.24, size * 0.24)
        text_x = cover.right() + 12
        text_w = max(24.0, w - text_x - 14)
        p.setBrush(_tc(theme.accent_fill))
        p.drawRoundedRect(QRectF(text_x, h / 2.0 - 5, text_w * 0.9, 4), 2, 2)
        soft = _tc(theme.text_muted)
        p.setBrush(soft)
        p.drawRoundedRect(QRectF(text_x, h / 2.0 + 5, text_w * 0.6, 3), 1.5, 1.5)

        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_tc(theme.border), 1))
        p.drawRoundedRect(rect, radius, radius)
        p.end()


class _ThemeSwatchButton(QPushButton):
    """Theme card: mini preview + name + check mark (not colour-only)."""

    _NAMES = {"ink": "墨", "celadon": "青瓷"}

    def __init__(self, theme_id, tr, parent=None):
        super().__init__(parent)
        self._tr = tr
        self.theme_id = theme_id
        self._appearance = "dark"
        self.setObjectName("themeSwatch")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.name = QLabel()
        self.name.setObjectName("themeSwatchName")
        self.check = QLabel("\u2713")
        self.check.setObjectName("themeSwatchCheck")
        self.check.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.check.setVisible(False)
        top.addWidget(self.name)
        top.addStretch(1)
        top.addWidget(self.check)
        lay.addLayout(top)
        self.preview = _ThemePreview(self)
        lay.addWidget(self.preview, 1)
        self.set_appearance("dark")
        self.retranslate()

    def set_appearance(self, appearance):
        appearance = "light" if appearance == "light" else "dark"
        self._appearance = appearance
        theme = ui_theme.THEMES[self.theme_id][self._appearance]
        self.preview.set_theme(theme)
        self.check.setStyleSheet(
            "QLabel#themeSwatchCheck{color:%s;font-size:13px;font-weight:700;}"
            % theme.text)

    def setChecked(self, checked):
        super().setChecked(checked)
        self.check.setVisible(bool(checked))

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
        # 数字大、单位小：iOS 的统计卡都是这个排法，等宽同号会显得笨重
        m = re.match(r"^(.+?)\s+(分钟|小时|天|首|次)$", text.strip())
        if m:
            self.value.setText(
                f'<span style="font-size:27px;font-weight:700;">{m.group(1)}</span>'
                f'<span style="font-size:14px;font-weight:500;">&nbsp;{m.group(2)}</span>')
        else:
            self.value.setText(text)


class _EmptyGlyph(QWidget):
    """Outlined note inside a hairline circle for the report empty state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(76, 76)
        self._line = QColor("#8A8A8F")
        self._ink = QColor("#625D55")

    def set_theme(self, theme):
        self._line = _tc(theme.border_strong)
        self._ink = _tc(theme.text_muted)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self._line, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(1.5, 1.5, 73, 73))
        # 自己画音符：图标集里的 note 在 26px 下只剩一根歪线，像坏图。
        p.setPen(Qt.NoPen)
        p.setBrush(self._ink)
        p.drawEllipse(QRectF(24, 40, 15, 11))
        p.setPen(QPen(self._ink, 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(38, 45), QPointF(38, 24))
        p.drawLine(QPointF(38, 24), QPointF(49, 28))
        p.end()


class _RankList(QWidget):
    """Ranked list with real columns: 序号 / 名称·歌手 / 时长。

    A single QLabel joined with spaces produced ragged columns (CJK and Latin
    names have different widths), so long titles drifted into the duration
    column. This widget elides the name and right-aligns a tabular duration.
    """

    ROW_H = 26

    def __init__(self, tr, show_artist=False, parent=None):
        super().__init__(parent)
        self._tr = tr
        self._show_artist = bool(show_artist)
        self._rows = []
        self._text = QColor("#F3F0E9")
        self._muted = QColor("#A6A6AB")
        self._secondary = QColor("#B0ADA5")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.ROW_H)

    def set_theme(self, theme):
        self._text = _tc(theme.text)
        self._muted = _tc(theme.text_muted)
        self._secondary = _tc(theme.text_secondary)
        self.update()

    def set_rows(self, rows):
        self._rows = list(rows or [])[:5]
        self.setMinimumHeight(max(self.ROW_H, self.ROW_H * max(1, len(self._rows))))
        self.updateGeometry()
        self.update()

    def paintEvent(self, _event):
        if not self._rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = _pick_ui_font(12)
        p.setFont(font)
        fm = QFontMetrics(font)
        w = self.width()
        dur_w = 58
        rank_w = 24
        for i, row in enumerate(self._rows):
            name, artist, seconds = row
            y = i * self.ROW_H
            p.setPen(self._muted)
            p.drawText(QRectF(0, y, rank_w, self.ROW_H),
                       Qt.AlignLeft | Qt.AlignVCenter, "%02d" % (i + 1))
            dur = _format_duration(seconds, self._tr)
            p.setPen(self._secondary)
            p.drawText(QRectF(w - dur_w, y, dur_w, self.ROW_H),
                       Qt.AlignRight | Qt.AlignVCenter, dur)
            name_w = w - rank_w - dur_w - 10
            p.setPen(self._text)
            p.drawText(QRectF(rank_w, y, name_w, self.ROW_H),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(name, Qt.ElideRight,
                                     max(40, int(name_w)))
                       if not (artist and self._show_artist)
                       else fm.elidedText(name, Qt.ElideRight,
                                          max(40, int(name_w * 0.56)))
                       )
            if artist and self._show_artist:
                meta_w = name_w * 0.44
                p.setPen(self._muted)
                p.drawText(QRectF(rank_w + name_w * 0.58, y,
                                  max(10, meta_w), self.ROW_H),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText("· " + artist, Qt.ElideRight,
                                         max(10, int(meta_w)))
                           )
        p.end()


class ReportPage(QWidget):
    clear_requested = Signal()
    play_requested = Signal()

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
        self.clear_btn = ui_glass.GlassButton(
            tr("清空听歌数据"), variant=ui_glass.DANGER)
        self.clear_btn.setObjectName("dangerGhost")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        head.addWidget(self.clear_btn)
        root.addLayout(head)

        # 有数据才出现的整块内容：空态时整块换成一张居中卡片，而不是留一堆
        # 隐藏了子控件的空壳（旧实现里 hero 带 stretch，空态会撑出 480px 空白）。
        self.data_box = QWidget()
        self.data_box.setObjectName("reportData")
        dl = QVBoxLayout(self.data_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(14)

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
        dl.addWidget(hero, 1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.today = StatTile(tr("今日听歌时长"))
        self.peak = StatTile(tr("本月最爱时段"))
        self.streak = StatTile(tr("连续听歌"))
        self.active = StatTile(tr("活跃天数"))
        for i, w in enumerate((self.today, self.peak, self.streak, self.active)):
            grid.addWidget(w, 0, i)
        dl.addLayout(grid)

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
        self.artist_rank = _RankList(tr, show_artist=False)
        al.addWidget(self.artist_rank)
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
        self.track_rank = _RankList(tr, show_artist=True)
        tl.addWidget(self.track_rank)
        self.track_spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        tl.addItem(self.track_spacer)
        bottom.addWidget(self.track_card, 1)
        dl.addLayout(bottom, 1)
        root.addWidget(self.data_box, 1)

        # ---- 空态：一张居中的卡片，而不是底部一条孤立的提示 ----
        self.empty_card = QFrame()
        self.empty_card.setObjectName("reportEmptyCard")
        el = QVBoxLayout(self.empty_card)
        el.setContentsMargins(32, 30, 32, 34)
        el.setSpacing(10)
        el.addStretch(1)
        self.empty_glyph = _EmptyGlyph()
        el.addWidget(self.empty_glyph, 0, Qt.AlignHCenter)
        self.empty_title = QLabel(tr("还没有听歌记录"))
        self.empty_title.setObjectName("reportEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        el.addWidget(self.empty_title)
        self.empty_hint = QLabel(
            tr("播放满 20 秒才会开始统计；报告只在本机计算，不上传。"))
        self.empty_hint.setObjectName("reportEmptyHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        el.addWidget(self.empty_hint)
        self.empty_go = ui_glass.GlassButton(tr("去听一首"), variant=ui_glass.ACCENT)
        self.empty_go.setObjectName("emptyGo")
        self.empty_go.setFixedHeight(34)
        self.empty_go.setCursor(Qt.PointingHandCursor)
        self.empty_go.clicked.connect(self.play_requested.emit)
        el.addWidget(self.empty_go, 0, Qt.AlignHCenter)
        el.addStretch(1)
        root.addWidget(self.empty_card, 1)
        self.empty_card.setVisible(False)

    def set_theme(self, theme):
        self.clear_btn.set_theme(theme)
        self.empty_go.set_theme(theme)
        self.empty_glyph.set_theme(theme)
        self.artist_rank.set_theme(theme)
        self.track_rank.set_theme(theme)

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
        self.empty_title.setText(self._tr("还没有听歌记录"))
        self.empty_hint.setText(
            self._tr("播放满 20 秒才会开始统计；报告只在本机计算，不上传。"))
        self.empty_go.setText(self._tr("去听一首"))
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
        else:
            self.artist_big.setText("—")
            self.artist_meta.setText(self._tr("暂无数据"))
        self.artist_rank.set_rows(
            [(a.get("name") or "", "", a.get("seconds", 0)) for a in top[1:5]])
        tracks = s.get("top_tracks") or []
        self.track_rank.set_rows(
            [(t.get("title") or "", t.get("artist") or "", t.get("seconds", 0))
             for t in tracks[:5]])
        self.data_box.setVisible(has_data)
        self.empty_card.setVisible(not has_data)
        # 空态下「清空」没有可清的东西：禁用按钮还留着反而像个灰亏的陷阱
        self.clear_btn.setVisible(has_data)
        self.clear_btn.setEnabled(has_data)


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
            tracks = _load_playlist_tracks(self.url)
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
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status.setToolTip(self.status.text())
        root.addWidget(self.status)
        self._apply_status_width()
        self._set_cover()
        self._set_accessible_name()

    def _status_width_texts(self):
        return ("✓ " + self._tr("歌词已就绪"), self._tr("未找到本地歌词"))

    def _apply_status_width(self):
        metrics = QFontMetrics(self.status.font())
        widest = max(metrics.horizontalAdvance(text)
                     for text in self._status_width_texts())
        self.status.setMinimumWidth(widest + 8)

    def _update_metadata_elide(self):
        for label, full in ((self.title, self._full_title),
                            (self.artist, self._full_artist)):
            metrics = QFontMetrics(label.font())
            label.setText(metrics.elidedText(
                full, Qt.ElideMiddle, max(1, label.width())))

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_status_width()
        self._update_metadata_elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._apply_status_width()

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
        if self.track.get("source") == "qqqueue":
            return self._tr("跟随 QQ 音乐")
        if self._has_local_lyrics():
            return "✓ " + self._tr("歌词已就绪")
        return self._tr("未找到本地歌词")

    def _update_status_state(self):
        matched = self._has_local_lyrics()
        self.status.setProperty("matched", "1" if matched else "0")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(self._status_text())
        self.status.setToolTip(self.status.text())
        self._apply_status_width()
        self._set_accessible_name()

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
    queue_requested = Signal()
    prev_requested = Signal()
    next_requested = Signal()

    def __init__(self, tr, parent=None, cover_loader=None, lyrics_loader=None):
        super().__init__(parent)
        self._tr = tr
        self._cover_loader = cover_loader
        self._lyrics_loader = lyrics_loader
        self._theme = None
        self._tracks = []
        self._state = "empty"
        self._selected_track = None
        self._fetch_thread = None
        self._cancelled = False
        self._fetch_generation = 0
        self.setObjectName("playlistPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 28)
        root.setSpacing(16)

        self.title = QLabel(tr("歌单"))
        self.title.setObjectName("playlistPageTitle")
        self.subtitle = QLabel(tr("导入歌单或读取 QQ 音乐列表；用上一首 / 下一首切歌。"))
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
        self.url_input.setPlaceholderText(tr("粘贴歌单链接或 M3U/M3U8"))
        self.url_input.setAccessibleName(self.url_input.placeholderText())
        self.url_input.setAccessibleDescription(
            self.url_input.placeholderText())
        self.url_input.setFixedHeight(40)
        self.url_input.returnPressed.connect(self._import_url)
        form.addWidget(self.url_input, 1)
        self.import_btn = ui_glass.GlassButton(
            tr("导入歌单"), variant=ui_glass.ACCENT)
        self.import_btn.setObjectName("primary")
        self.import_btn.setFixedHeight(40)
        self.import_btn.clicked.connect(self._import_url)
        form.addWidget(self.import_btn)
        self.file_btn = ui_glass.GlassButton(
            tr("从文件导入…"), variant=ui_glass.GLASS)
        self.file_btn.setObjectName("ghost")
        self.file_btn.setFixedHeight(40)
        self.file_btn.clicked.connect(self._import_file)
        form.addWidget(self.file_btn)
        self.cancel_btn = ui_glass.GlassButton(
            tr("取消"), variant=ui_glass.GLASS)
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setFixedHeight(40)
        self.cancel_btn.clicked.connect(self._cancel_import)
        self.cancel_btn.hide()
        form.addWidget(self.cancel_btn)
        panel_lay.addLayout(form)
        queue_row = QHBoxLayout()
        queue_row.setSpacing(8)
        self.queue_btn = ui_glass.GlassButton(
            tr("读取 QQ 音乐列表"), variant=ui_glass.GLASS)
        self.queue_btn.setObjectName("ghost")
        self.queue_btn.setFixedHeight(36)
        self.queue_btn.clicked.connect(self.queue_requested.emit)
        queue_row.addWidget(self.queue_btn)
        queue_row.addStretch(1)
        self.compliance = QLabel(tr("仅导入歌单信息，不获取音乐音频或版权歌词。"))
        self.compliance.setObjectName("playlistCompliance")
        self.compliance.setWordWrap(True)
        queue_row.addWidget(self.compliance)
        panel_lay.addLayout(queue_row)
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
        self.prev_btn = ui_glass.GlassButton(
            tr("上一首"), variant=ui_glass.GLASS)
        self.prev_btn.setObjectName("ghost")
        self.prev_btn.setFixedHeight(30)
        self.prev_btn.clicked.connect(self.prev_requested.emit)
        self.next_btn = ui_glass.GlassButton(
            tr("下一首"), variant=ui_glass.GLASS)
        self.next_btn.setObjectName("ghost")
        self.next_btn.setFixedHeight(30)
        self.next_btn.clicked.connect(self.next_requested.emit)
        head.addWidget(self.prev_btn)
        head.addWidget(self.next_btn)
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
        button = ui_glass.GlassButton(
            self._tr("导入歌单"), variant=ui_glass.ACCENT)
        button.setObjectName("primary")
        button.setFixedHeight(40)
        button.clicked.connect(self._import_file)
        if self._theme is not None:
            button.set_theme(self._theme)
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

    def set_queue_loading(self, loading: bool):
        self.queue_btn.setEnabled(not loading)
        self.queue_btn.setText(
            self._tr("正在读取 QQ 音乐列表…") if loading
            else self._tr("读取 QQ 音乐列表"))

    def set_theme(self, theme):
        self._theme = theme
        for button in (self.import_btn, self.file_btn, self.cancel_btn,
                       self.queue_btn, self.prev_btn, self.next_btn):
            button.set_theme(theme)
        self.refresh()

    def show_notice(self, text: str, error: bool = False):
        if not text:
            self.error.hide()
            self.success.hide()
            return
        label = self.error if error else self.success
        label.setText(text)
        (self.success if not error else self.error).hide()
        label.show()

    def _set_import_ready(self):
        self.url_input.setProperty("error", "0")
        self.url_input.style().unpolish(self.url_input)
        self.url_input.style().polish(self.url_input)
        self.url_input.setEnabled(True)
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
        self.success.hide()
        self.url_input.setEnabled(False)
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
        self._fetch_generation += 1
        if self._fetch_thread is not None:
            try:
                self._fetch_thread.completed.disconnect()
                self._fetch_thread.failed.disconnect()
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
        self.url_input.setPlaceholderText(self._tr("粘贴歌单链接或 M3U/M3U8"))
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
        if self._state == "loading":
            return
        raw = self.url_input.text().strip()
        url = _extract_playlist_url(raw) or raw
        if url != raw:
            self.url_input.setText(url)
        if not url:
            self.set_error(self._tr(
                "无法读取这个歌单。请使用 M3U/M3U8 或支持平台的公开歌单链接。"))
            return
        try:
            parsed = urllib.parse.urlparse(url)
        except ValueError:
            self.set_error(self._tr(
                "无法读取这个歌单。请使用 M3U/M3U8 或支持平台的公开歌单链接。"))
            return
        host = parsed.hostname or ""
        if _playlist_is_platform_url(host) and not _playlist_platform_kind(host):
            self.set_error(self._tr(
                "这个平台链接暂不支持，目前支持 QQ 音乐 / 网易云 / 酷狗 / 酷我 / 咪咕 的公开歌单；其他平台请导出 M3U/M3U8。"))
            return
        self._cancelled = False
        self._fetch_generation += 1
        generation = self._fetch_generation
        self.set_loading()
        self._fetch_thread = PlaylistFetchThread(url, self)
        self._fetch_thread.completed.connect(
            lambda tracks, g=generation: self._on_fetch_completed(g, tracks))
        self._fetch_thread.failed.connect(
            lambda message, g=generation: self._on_fetch_failed(g, message))
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

    def _on_fetch_completed(self, generation, tracks):
        if generation != self._fetch_generation:
            return
        self._fetch_thread = None
        self._set_import_ready()
        if self._cancelled:
            return
        if not tracks:
            self.set_error(self._tr(
                "无法读取这个歌单。请使用 M3U/M3U8 或支持平台的公开歌单链接。"))
            return
        self.set_tracks(tracks)

    def _on_fetch_failed(self, generation, message):
        if generation != self._fetch_generation:
            return
        self._fetch_thread = None
        self._set_import_ready()
        if self._cancelled:
            return
        self.set_error(_playlist_error_message(message, self._tr))


HistoryPage = PlaylistPage
class MainPlayerWindow(QWidget):
    closed = Signal()
    qq_queue_ready = Signal(object)

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
        from shiboken6 import isValid

        manager = getattr(self.ov, "theme_manager", None)
        if manager is not None and not isValid(manager):
            manager = None
        reduce_motion = True if self.ov.cfg.get("reduce_motion") else None
        if manager is None:
            theme_id = str(self.ov.cfg.get("theme_id") or "ink")
            appearance = str(self.ov.cfg.get("appearance") or "system")
            if theme_id not in ui_theme.THEMES:
                theme_id = "ink"
            if appearance not in ui_theme.APPEARANCES:
                appearance = "system"
            # The overlay outlives the player window, so it owns the manager.
            # Parenting to the window makes overlay.theme_manager a dangling
            # wrapper after close/deleteLater, breaking the next open.
            manager = ui_theme.ThemeManager(
                theme_id, appearance, self.ov, reduce_motion=reduce_motion)
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
        self.report.play_requested.connect(lambda: self.navigate("now"))
        self.playlist = PlaylistPage(
            self._tr,
            cover_loader=_history_cover_loader,
            lyrics_loader=self._playlist_lyrics_loader)
        self.history = self.playlist
        self.playlist.track_selected.connect(self._open_playlist_track)
        self.playlist.queue_requested.connect(self._load_qq_queue)
        self.playlist.prev_requested.connect(
            lambda: self.ov.media_command("prev"))
        self.playlist.next_requested.connect(
            lambda: self.ov.media_command("next"))
        self.qq_queue_ready.connect(self._on_qq_queue)
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
        for widget in (self.titlebar, self.sidebar, self.now, self.grip,
                       self.settings_page, self.report, self.playlist):
            setter = getattr(widget, "set_theme", None)
            if callable(setter):
                setter(theme)
        self.report.spark.set_theme(theme)
        self._sync_glass_motion(theme)

    def _sync_glass_motion(self, theme):
        """Glass buttons animate unless the user asked for reduced motion."""
        manager = getattr(self.ov, "theme_manager", None)
        if manager is not None:
            reduce = manager.reduce_motion()
        else:
            reduce = bool(self.ov.cfg.get("reduce_motion"))
        duration = 0 if reduce else int(getattr(theme, "m_fast", 140))
        for button in self.findChildren(ui_glass.GlassButton):
            button.set_motion(duration)
        # 歌词滚动同样是动画：「减少动态效果」开启时直接落位，不做惯性与回弹
        try:
            self.now.canvas.set_reduce_motion(reduce)
        except (AttributeError, RuntimeError):
            pass

    def _apply_theme(self, theme):
        self._apply_style()
        self._refresh_now(force=True)
        # The standalone overlay settings window is a separate top-level
        # widget; refresh it too if it is currently open.
        panel = getattr(self.ov, "panel", None)
        if panel is not None:
            try:
                panel.set_theme(theme)
            except (RuntimeError, AttributeError):
                pass

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
        # 标题栏左上角永远是「图标 + 应用名」；页面名只是后面一条弱化的
        # crumb。报告页已有 H1 + 副标题，再来一条 crumb 就是同义重复。
        self.titlebar.page_label.setVisible(key != "report")
        if key == "now":
            self.stack.setCurrentWidget(self.now)
            self.titlebar.page_label.setText(self._tr("正在播放"))
        elif key == "report":
            self.stack.setCurrentWidget(self.report)
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
            self.titlebar.page_label.setText(self._tr("桌面歌词设置"))
        self._animate_page(self.stack.currentWidget())

    def _animate_page(self, page):
        """Page switches are instant.

        The old 180ms opacity fade pushed the page through an offscreen
        surface; switching to the playlist left the playing stage ghosted
        over the new page and made every navigation feel slow on top of the
        extra render target.
        """
        if page is None:
            return
        old = getattr(page, "_page_anim", None)
        if old is not None:
            try:
                old.stop()
            except RuntimeError:
                pass
            page._page_anim = None
        if page.graphicsEffect() is not None:
            page.setGraphicsEffect(None)

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
        self.navigate("now")

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
            self.ov._notify(self._tr("桌面歌词"), self._tr("已切换到迷你歌词"))
        except Exception:
            pass

    def toggle_immersive(self):
        self._immersive = not self._immersive
        if self._immersive:
            self.navigate("now")
            self.sidebar.hide()
            self.titlebar.hide()
            if not self.isFullScreen():
                self.showFullScreen()
        else:
            self.sidebar.show()
            self.titlebar.show()
            if self.isFullScreen():
                self.showNormal()
            else:
                self.show()
        self.now.set_immersive(self._immersive)
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

    def _load_qq_queue(self):
        self.playlist.set_queue_loading(True)
        self.playlist.show_notice("")

        def work():
            try:
                res = self.ov.read_qq_queue()
            except Exception:
                res = {"ok": False, "reason": "exception"}
            self.qq_queue_ready.emit(res)

        threading.Thread(target=work, daemon=True, name="qq-queue-ui").start()

    def _on_qq_queue(self, res):
        self.playlist.set_queue_loading(False)
        res = res or {}
        if not res.get("ok"):
            self.playlist.show_notice(
                self._tr("请先打开 QQ 音乐「播放队列」"), error=True)
            return
        rows = res.get("rows") or []
        tracks = [{"title": row["title"], "artist": row.get("artist") or "",
                   "duration": 0.0, "cover": "", "source": "qqqueue"}
                  for row in rows]
        self.playlist.set_tracks(tracks)
        self.playlist.show_notice(
            self._tr("已读取 %d 首（仅展示，切歌请用上/下一首）") % len(tracks))

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
            # 歌词逐字高亮跟着 90ms 心跳走只有 11fps，肉眼看就是"卡"。
            # 播放中且停在歌词页时提到 ~60fps；其它页面回到低频巡检，
            # 避免空转整窗重绘。
            want = 16 if (self._page == "now"
                          and self.ov.status == "PLAYING") else 90
            if self._timer.interval() != want:
                self._timer.setInterval(want)
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
