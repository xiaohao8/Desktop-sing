# -*- coding: utf-8 -*-
"""Lyrics lookup and local cache access."""
from __future__ import annotations

import importlib
import json
import os
from typing import Any


class LyricsService:
    def __init__(self, runtime: Any = None):
        self._runtime = runtime

    @property
    def runtime(self):
        if self._runtime is None:
            self._runtime = importlib.import_module("lyrics_overlay")
        return self._runtime

    def fetch(self, title: str, artist: str, *, prefer_netease: bool = False,
              duration: float = 0.0, strict_artist: bool = False):
        return self.runtime.fetch_lyrics(
            title,
            artist,
            prefer_netease=prefer_netease,
            duration=duration,
            strict_artist=strict_artist,
        )

    def cache_path(self, title: str, artist: str) -> str:
        runtime = self.runtime
        key = (
            "%s|%s"
            % (
                runtime.clean_query_text(title or ""),
                runtime.clean_query_text(artist or ""),
            )
        ).lower().strip()
        return runtime._cache_path(key)

    def load_cached(self, title: str, artist: str) -> tuple[list, dict[int, str]]:
        """Return cached display lines and a line-index -> translation map."""
        try:
            with open(self.cache_path(title, artist), encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError, TypeError):
            return [], {}

        if isinstance(raw, dict):
            lines = raw.get("lines") or []
            translations = raw.get("trans") or []
        elif isinstance(raw, list):
            lines = raw
            translations = []
        else:
            return [], {}

        trans_map: dict[int, str] = {}
        for index, (line_time, _text) in enumerate(lines):
            best, best_distance = "", 1.2
            for trans_time, trans_text in translations:
                try:
                    distance = abs(float(trans_time) - float(line_time))
                except (TypeError, ValueError):
                    continue
                if distance < best_distance:
                    best, best_distance = str(trans_text or ""), distance
            if best:
                trans_map[index] = best
        return lines, trans_map

    def clear_cache(self) -> int:
        return int(self.runtime.prune_cache(force=True) or 0)

    def cache_state(self) -> tuple[int, int]:
        return self.runtime.cache_size()
