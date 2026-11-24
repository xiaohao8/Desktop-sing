# -*- coding: utf-8 -*-
"""Application service container."""
from __future__ import annotations

import importlib

from .context import AppContext
from .lyrics_service import LyricsService
from .media_service import MediaService
from .shell import WindowShell


class ApplicationRuntime:
    def __init__(self, context: AppContext, watcher_factory=None, overlay=None):
        runtime = context._runtime or importlib.import_module("lyrics_overlay")
        self.context = context
        watcher = (watcher_factory or runtime.MediaWatcher)()
        self.media = MediaService(watcher)
        self.lyrics = LyricsService(runtime)
        self.overlay = overlay or runtime.LyricOverlay(watcher, context=context)
        self.overlay.context = context
        self.overlay.lyrics_service = self.lyrics
        self.shell = WindowShell(self.overlay)
        self.overlay.window_shell = self.shell
        self._started = False

    def start(self):
        if self._started:
            return
        self.media.start()
        self.overlay.show()
        self._started = True

    @property
    def started(self) -> bool:
        return self._started
