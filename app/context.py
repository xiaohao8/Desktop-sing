# -*- coding: utf-8 -*-
"""Runtime paths, version and launch policy."""
from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any


@dataclass(frozen=True)
class AppPaths:
    app_dir: str
    config_dir: str
    cache_dir: str
    config_path: str
    listening_path: str
    font_dir: str
    log_path: str


@dataclass
class AppContext:
    version: str
    argv: list[str]
    paths: AppPaths
    store_mode: bool
    boot_ts: float
    config: dict[str, Any]
    language: str
    _runtime: Any = None

    @classmethod
    def from_runtime(cls, runtime: Any, argv: list[str] | None = None) -> "AppContext":
        import listening_store

        args = list(argv if argv is not None else [])
        config = runtime.load_config()
        paths = AppPaths(
            app_dir=runtime.APP_DIR,
            config_dir=runtime.CFG_DIR,
            cache_dir=runtime.CACHE_DIR,
            config_path=runtime.CONFIG_PATH,
            listening_path=listening_store.default_path(),
            font_dir=runtime.USER_FONT_DIR,
            log_path=os.path.join(runtime.CFG_DIR, "desktop-lyrics.log"),
        )
        return cls(
            version=str(runtime.APP_VERSION),
            argv=args,
            paths=paths,
            store_mode=bool(runtime.STORE_MODE),
            boot_ts=float(getattr(runtime, "_BOOT_TS", time.time())),
            config=config,
            language=str(config.get("ui_lang", "auto") or "auto"),
            _runtime=runtime,
        )

    @property
    def startup_launch(self) -> bool:
        return any(
            arg.lower() in ("--startup", "--startup-task", "--mini")
            for arg in self.argv[1:]
        )

    @property
    def should_open_player(self) -> bool:
        open_player = bool(self.config.get("open_player_on_start", True))
        if self.startup_launch:
            return False
        if self.store_mode and time.time() - self.boot_ts < 90.0:
            return False
        return open_player

    def save_config(self, config: dict[str, Any] | None = None) -> None:
        target = self.config if config is None else config
        self.config = target
        if self._runtime is not None:
            self._runtime.save_config(target)
