# -*- coding: utf-8 -*-
"""Local listening history and report data.

Privacy boundary:
  * only song title / artist / date / hour / played seconds / play count /
    last-played timestamp are stored;
  * no file paths, account ids, device ids, IP addresses or raw audio;
  * the file never leaves this computer.

The data is deliberately aggregated by day + track instead of storing every tick.
That keeps the report useful while limiting the footprint to a few hundred KB.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading
import time

APP_NAME = "Desktop-sing"
MIN_PLAY_SECONDS = 20.0
MAX_ENTRIES = 5000
RETENTION_DAYS = 365


def default_path() -> str:
    override = (os.environ.get("DESKTOP_SING_LISTEN_PATH") or "").strip()
    if override:
        return override
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    return os.path.join(base, "listening.json")


def _track_key(title: str, artist: str) -> str:
    return ("%s\x1f%s" % ((title or "").strip().lower(),
                          (artist or "").strip().lower()))


def _day(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _hour(ts: float) -> int:
    return int(_dt.datetime.fromtimestamp(ts).hour)


def _fmt_minutes(seconds: float) -> int:
    return max(0, int(round(float(seconds or 0.0) / 60.0)))


class ListeningStore:
    """Small atomic JSON store for listening sessions."""

    def __init__(self, path: str = ""):
        self.path = path or default_path()
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and isinstance(raw.get("sessions"), list):
                return {"v": 1, "sessions": [s for s in raw["sessions"]
                                             if isinstance(s, dict)]}
        except (OSError, ValueError, TypeError):
            pass
        return {"v": 1, "sessions": []}

    def save(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, separators=(",", ":"))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            except OSError:
                try:
                    if os.path.exists(self.path + ".tmp"):
                        os.remove(self.path + ".tmp")
                except OSError:
                    pass

    def add_session(self, title: str, artist: str, album: str = "",
                    source: str = "", seconds: float = 0.0,
                    started_at: float | None = None,
                    plays: int = 0,
                    total_seconds: float | None = None) -> bool:
        title = (title or "").strip()
        artist = (artist or "").strip()
        seconds = max(0.0, float(seconds or 0.0))
        total = max(0.0, float(total_seconds if total_seconds is not None
                               else seconds))
        plays = max(0, int(plays or 0))
        # Only a final, accepted session may create a report row. A partial
        # refresh before 20 seconds must not become visible.
        if not title:
            return False
        ts = float(started_at or time.time())
        day = _day(ts)
        hour = _hour(ts)
        key = _track_key(title, artist)
        with self._lock:
            found = None
            for s in self.data["sessions"]:
                if s.get("d") == day and s.get("k") == key:
                    found = s
                    break
            # A report refresh may persist a partial session. The final flush
            # then only adds the remaining seconds and the play count, so the
            # minimum must be evaluated against the whole session, not the
            # delta being committed now.
            persisted = float(found.get("s") or 0.0) if found else 0.0
            if max(total, persisted + seconds) < MIN_PLAY_SECONDS:
                return False
            if found is None:
                # Album/source are intentionally not persisted: they are not
                # needed for the report and would collect more than necessary.
                found = {"d": day, "k": key, "t": title, "a": artist,
                         "s": 0.0, "n": 0, "h": hour, "last": ts}
                self.data["sessions"].append(found)
            found["s"] = float(found.get("s") or 0.0) + seconds
            found["n"] = int(found.get("n") or 0) + plays
            found["last"] = max(float(found.get("last") or 0.0), ts)
            self._prune()
            self.save()
        return True

    def _prune(self, now: float | None = None):
        now = float(now or time.time())
        cutoff = now - RETENTION_DAYS * 86400.0
        sessions = []
        for s in self.data.get("sessions", []):
            try:
                last = float(s.get("last") or 0.0)
            except (TypeError, ValueError):
                continue
            if last >= cutoff:
                sessions.append(s)
        sessions.sort(key=lambda x: float(x.get("last") or 0.0))
        if len(sessions) > MAX_ENTRIES:
            sessions = sessions[-MAX_ENTRIES:]
        self.data["sessions"] = sessions

    def clear(self):
        with self._lock:
            self.data = {"v": 1, "sessions": []}
            self.save()

    def recent_tracks(self, limit: int = 20) -> list[dict]:
        with self._lock:
            grouped = {}
            for s in self.data.get("sessions", []):
                key = s.get("k") or _track_key(s.get("t", ""), s.get("a", ""))
                item = grouped.get(key)
                if item is None:
                    item = {"title": s.get("t", ""), "artist": s.get("a", ""),
                            "seconds": 0.0, "plays": 0, "last": 0.0, "days": set()}
                    grouped[key] = item
                item["seconds"] += float(s.get("s") or 0.0)
                item["plays"] += int(s.get("n") or 0)
                item["last"] = max(item["last"], float(s.get("last") or 0.0))
                item["days"].add(s.get("d", ""))
            rows = sorted(grouped.values(), key=lambda x: x["last"], reverse=True)
            for r in rows:
                r["days"] = len(r["days"])
                r["minutes"] = _fmt_minutes(r["seconds"])
            return rows[:max(1, int(limit))]

    def stats(self, now: float | None = None) -> dict:
        now = float(now or time.time())
        today = _dt.datetime.fromtimestamp(now).date()
        month_key = today.strftime("%Y-%m")
        sessions = list(self.data.get("sessions", []))
        total_s = today_s = month_s = 0.0
        plays = 0
        month_tracks = set()
        artists = {}
        tracks = {}
        hours = {}
        active_days = set()
        day_seconds = {}
        for s in sessions:
            try:
                sec = float(s.get("s") or 0.0)
            except (TypeError, ValueError):
                continue
            d = str(s.get("d") or "")
            if not d:
                continue
            total_s += sec
            day_seconds[d] = day_seconds.get(d, 0.0) + sec
            active_days.add(d)
            if d == today.strftime("%Y-%m-%d"):
                today_s += sec
            if d.startswith(month_key):
                month_s += sec
                plays += int(s.get("n") or 0)
                if s.get("k"):
                    month_tracks.add(s.get("k"))
            artist = (s.get("a") or "").strip()
            title = (s.get("t") or "").strip()
            if artist:
                artists[artist] = artists.get(artist, 0.0) + sec
            key = _track_key(title, artist)
            if key not in tracks:
                tracks[key] = {"title": title, "artist": artist,
                               "seconds": 0.0, "plays": 0}
            tracks[key]["seconds"] += sec
            tracks[key]["plays"] += int(s.get("n") or 0)
            try:
                h = int(s.get("h", 0)) % 24
            except (TypeError, ValueError):
                h = 0
            hours[h] = hours.get(h, 0.0) + sec

        # Consecutive active days, ending today or yesterday.
        streak = 0
        cursor = today if today.strftime("%Y-%m-%d") in active_days \
            else today - _dt.timedelta(days=1)
        while cursor.strftime("%Y-%m-%d") in active_days:
            streak += 1
            cursor -= _dt.timedelta(days=1)

        daily = []
        for i in range(6, -1, -1):
            d = today - _dt.timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            daily.append({"date": key, "label": d.strftime("%m/%d"),
                          "seconds": day_seconds.get(key, 0.0),
                          "minutes": _fmt_minutes(day_seconds.get(key, 0.0))})

        top_artists = sorted(artists.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_tracks = sorted(tracks.values(), key=lambda x: x["seconds"], reverse=True)[:8]
        peak_hour = max(hours.items(), key=lambda kv: kv[1])[0] if hours else 0
        return {
            "total_seconds": total_s,
            "total_minutes": _fmt_minutes(total_s),
            "today_seconds": today_s,
            "today_minutes": _fmt_minutes(today_s),
            "month_seconds": month_s,
            "month_minutes": _fmt_minutes(month_s),
            "month_plays": plays,
            "month_tracks": len(month_tracks),
            "unique_tracks": len(tracks),
            "active_days": len(active_days),
            "streak": streak,
            "peak_hour": "%02d:00" % peak_hour if hours else "--:--",
            "top_artist": (top_artists[0][0] if top_artists else ""),
            "top_artist_minutes": _fmt_minutes(top_artists[0][1]) if top_artists else 0,
            "top_artists": [{"name": n, "seconds": s,
                             "minutes": _fmt_minutes(s)}
                            for n, s in top_artists],
            "top_tracks": [{"title": t["title"], "artist": t["artist"],
                            "seconds": t["seconds"],
                            "minutes": _fmt_minutes(t["seconds"]),
                            "plays": t["plays"]} for t in top_tracks],
            "daily": daily,
        }


class ListeningTracker:
    """Accumulate real playing seconds from the existing media tick stream.

    Seconds are sampled from the existing media tick stream. Report refreshes
    may persist the current delta, while final flushes count the play exactly
    once. Short previews (< 20 s) are ignored entirely.
    """

    def __init__(self, store: ListeningStore, enabled=None):
        self.store = store
        self._enabled = enabled or (lambda: True)
        self._enabled_default = enabled is None
        self._song = None
        self._song_key = None
        self._status = ""
        self._last_mono = None
        self._seconds = 0.0
        self._persisted_seconds = 0.0
        self._play_counted = False
        self._started_at = None

    def on_media(self, info):
        incoming_key = None
        if info and (info.get("title") or "").strip():
            incoming_key = (_track_key(info.get("title", ""), info.get("artist", "")),
                            str(info.get("source") or ""))
        # Compare before the final flush: flushing clears the current session.
        same_track = (self._song is not None and incoming_key == self._song_key)
        if same_track:
            self._status = ""
            self._last_mono = time.monotonic()
            return
        self.flush(final=True)
        if info and (info.get("title") or "").strip():
            self._song = dict(info)
            self._song_key = incoming_key
            self._started_at = time.time()
            self._seconds = 0.0
            self._persisted_seconds = 0.0
            self._play_counted = False
        else:
            self._song = None
            self._song_key = None
            self._started_at = None
            self._seconds = 0.0
            self._persisted_seconds = 0.0
            self._play_counted = False
        self._status = ""
        self._last_mono = time.monotonic()

    def on_tick(self, pos, duration, status):
        now = time.monotonic()
        if (self._last_mono is not None and self._song
                and self._status == "PLAYING" and self._tracking_on()):
            dt = now - self._last_mono
            # A suspended laptop or a stalled collector must not become listening time.
            if 0.0 < dt <= 2.5:
                self._seconds += dt
        self._last_mono = now
        self._status = status

    def flush(self, final: bool = False, force: bool = False):
        """Persist the current session without duplicating play counts.

        ``final=False`` is used by report refreshes: it makes the current
        seconds visible immediately, but does not count a play. ``final=True``
        is used on track change, stop and exit: it commits the remaining
        seconds and increments the play counter once, provided the session
        reached the 20-second minimum. ``force=True`` commits the remaining
        seconds even when the user has just turned statistics off.
        """
        if self._song and (force or self._tracking_on()):
            delta = max(0.0, self._seconds - self._persisted_seconds)
            want_play = int(final and not self._play_counted
                            and self._seconds >= MIN_PLAY_SECONDS)
            # Partial refreshes are useful only after the track crossed the
            # threshold. Persisting a 5-second delta and then stopping would
            # otherwise leave a sub-threshold row in the report.
            if final or self._seconds >= MIN_PLAY_SECONDS:
                accepted = self.store.add_session(
                    self._song.get("title", ""), self._song.get("artist", ""),
                    self._song.get("album", ""), self._song.get("source", ""),
                    delta, self._started_at, plays=want_play,
                    total_seconds=self._seconds)
                if accepted:
                    self._persisted_seconds = self._seconds
                    if want_play:
                        self._play_counted = True
        if final:
            self._song = None
            self._song_key = None
            self._seconds = 0.0
            self._persisted_seconds = 0.0
            self._play_counted = False
            self._started_at = None

    def _tracking_on(self) -> bool:
        try:
            return bool(self._enabled())
        except Exception:
            return bool(self._enabled_default)

    def reset(self):
        """Discard the in-memory session without writing it to the store."""
        self._song = None
        self._song_key = None
        self._status = ""
        self._last_mono = None
        self._seconds = 0.0
        self._persisted_seconds = 0.0
        self._play_counted = False
        self._started_at = None

