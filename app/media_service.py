# -*- coding: utf-8 -*-
"""Thin media-service wrapper around the mature SMTC watcher."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class MediaService(QObject):
    media_changed = Signal(object)
    ticked = Signal(float, float, str)

    def __init__(self, watcher: QObject):
        super().__init__()
        self.watcher = watcher
        self._started = False
        watcher.mediaChanged.connect(self._forward_media)
        watcher.ticked.connect(self._forward_tick)

    @Slot(object)
    def _forward_media(self, info):
        self.media_changed.emit(info)

    @Slot(float, float, str)
    def _forward_tick(self, position, duration, status):
        self.ticked.emit(position, duration, status)

    def start(self) -> None:
        if not self._started:
            self.watcher.start()
            self._started = True

    def activate(self) -> None:
        self.watcher.activate()

    @property
    def started(self) -> bool:
        return self._started
