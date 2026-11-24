# -*- coding: utf-8 -*-
"""Window coordination for the player, mini bar and settings."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class WindowShell(QObject):
    player_opened = Signal()
    player_closed = Signal()
    mini_shown = Signal()

    def __init__(self, overlay, player_factory=None):
        super().__init__()
        self.overlay = overlay
        self.player = None
        self._player_factory = player_factory or self._create_player

    def _create_player(self):
        from lyrics_view import MainPlayerWindow

        return MainPlayerWindow(self.overlay)

    def open_player(self):
        try:
            if self.player is None:
                player = self._player_factory()
                self.player = player
                self.overlay.main_player = player
                player.closed.connect(self._on_player_closed)
                player.show()
                self.player_opened.emit()
                return player
            if self.player.isMinimized():
                self.player.showNormal()
            else:
                self.player.show()
            self.player.raise_()
            self.player.activateWindow()
            self.player_opened.emit()
            return self.player
        except Exception:
            import traceback

            from lyrics_overlay import log

            log("player window open failed:\n" + traceback.format_exc())
            try:
                self.overlay.tray.showMessage(
                    self.overlay._tr("桌面歌词"),
                    self.overlay._tr("播放器窗口打开失败，详情见日志"),
                    self.overlay.tray.Warning,
                    3000,
                )
            except Exception:
                pass
            return None

    def _on_player_closed(self):
        player, self.player = self.player, None
        self.overlay.main_player = None
        if player is not None:
            player.deleteLater()
        if not self.overlay.isVisible():
            self.overlay.show()
            try:
                self.overlay._save_position()
            except Exception:
                pass
        QTimer.singleShot(0, self.overlay._ensure_overlay_visible)
        self.player_closed.emit()

    def close_player(self):
        if self.player is not None:
            self.player.close()

    def open_report(self):
        player = self.open_player()
        if player is None:
            return
        try:
            self.overlay.listen_tracker.flush()
            player.open_report()
        except Exception:
            import traceback

            from lyrics_overlay import log

            log("report page open failed:\n" + traceback.format_exc())

    def show_mini(self):
        if self.player is not None:
            self.player.hide()
        self.overlay.show()
        try:
            self.overlay._ensure_overlay_visible()
        except Exception:
            pass
        try:
            self.overlay.tray.showMessage(
                self.overlay._tr("桌面歌词"),
                self.overlay._tr("已切换到迷你歌词"),
                self.overlay.tray.Information,
                1500,
            )
        except Exception:
            pass
        self.mini_shown.emit()

    def open_settings(self):
        player = self.open_player()
        if player is not None:
            player.navigate("settings")
            return
        self.overlay._open_panel()

    def refresh_player(self):
        if self.player is not None:
            self.player.refresh_all()

    def on_track_changed(self):
        if self.player is not None:
            self.player.on_track_changed()
