# -*- coding: utf-8 -*-
"""Application-framework smoke tests.

Run with:
    .buildenv312\\Scripts\\python.exe _test_app_framework.py
"""
import json
import os
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _cfg_sandbox  # noqa: E402

_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False,
                   open_player_on_start=False)

_tmp = tempfile.TemporaryDirectory(prefix="desktop-sing-framework-test-")
os.environ["DESKTOP_SING_LISTEN_PATH"] = os.path.join(_tmp.name, "listening.json")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from shiboken6 import isValid  # noqa: E402

import lyrics_overlay as L  # noqa: E402
from app.context import AppContext  # noqa: E402
from app.lyrics_service import LyricsService  # noqa: E402
from app.media_service import MediaService  # noqa: E402
from app.runtime import ApplicationRuntime  # noqa: E402


FAILS = []


def check(name, condition, detail=""):
    print(("  ok  - " if condition else "  FAIL- ") + name
          + ((" | " + str(detail)) if detail and not condition else ""))
    if not condition:
        FAILS.append(name)


class FakeWatcher(QObject):
    mediaChanged = Signal(object)
    ticked = Signal(float, float, str)

    def __init__(self):
        super().__init__()
        self.started = False
        self.activated = False

    def start(self):
        self.started = True

    def activate(self):
        self.activated = True


app = QApplication.instance() or QApplication([])
L._load_fonts()
L.set_ui_lang("zh-CN")

context = AppContext.from_runtime(L, ["Desktop-sing.exe", "--mini"])
check("上下文读取版本", context.version == L.APP_VERSION, context.version)
check("上下文使用真实配置目录",
      context.paths.config_dir == L.CFG_DIR, context.paths.config_dir)
check("上下文识别迷你启动", context.startup_launch)
check("迷你启动不自动打开播放器", not context.should_open_player)

normal = AppContext.from_runtime(L, ["Desktop-sing.exe"])
check("普通启动遵循主窗口偏好", normal.should_open_player is False,
      normal.config.get("open_player_on_start"))
normal.config["open_player_on_start"] = True
check("普通启动可打开主窗口", normal.should_open_player)
normal.config["open_player_on_start"] = False

watcher = FakeWatcher()
media = MediaService(watcher)
events = {"media": [], "ticks": []}
media.media_changed.connect(events["media"].append)
media.ticked.connect(lambda *args: events["ticks"].append(args))
media.start()
check("媒体服务启动底层采集器", watcher.started)
payload = {"title": "Test", "artist": "Artist"}
watcher.mediaChanged.emit(payload)
watcher.ticked.emit(12.5, 180.0, "PLAYING")
check("媒体事件透传", events["media"] == [payload], events["media"])
check("播放进度透传", events["ticks"] == [(12.5, 180.0, "PLAYING")],
      events["ticks"])

runtime = ApplicationRuntime(normal, watcher_factory=FakeWatcher)
check("运行时组装媒体服务", isinstance(runtime.media, MediaService))
check("运行时组装歌词服务", isinstance(runtime.lyrics, LyricsService))
check("运行时复用现有悬浮层", runtime.overlay.__class__ is L.LyricOverlay)
check("悬浮层绑定运行时上下文", runtime.overlay.context is normal)
check("悬浮层获得窗口协调器", runtime.overlay.window_shell is runtime.shell)

runtime.start()
check("运行时启动媒体并显示迷你条",
      runtime.media.started and runtime.overlay.isVisible())

service = LyricsService(L)
lines, trans = service.load_cached("不存在的测试歌曲", "不存在")
check("歌词缓存缺失时返回空结果", lines == [] and trans == {}, (lines, trans))

cache_dir = tempfile.mkdtemp(dir=_tmp.name)
old_cache_dir = L.CACHE_DIR
try:
    L.CACHE_DIR = cache_dir
    title, artist = "缓存测试", "测试歌手"
    path = service.cache_path(title, artist)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"v": 4, "lines": [[0.0, "第一句"], [3.0, "第二句"]],
                   "trans": [[0.1, "First"], [3.1, "Second"]],
                   "words": {}, "sk": True, "roma": []},
                  handle, ensure_ascii=False)
    cached_lines, cached_trans = service.load_cached(title, artist)
    check("歌词服务读取本地缓存",
          cached_lines == [[0.0, "第一句"], [3.0, "第二句"]], cached_lines)
    check("歌词服务映射翻译", cached_trans == {0: "First", 1: "Second"},
          cached_trans)
    service.clear_cache()
    check("歌词服务可清理缓存", not os.path.exists(path))
finally:
    L.CACHE_DIR = old_cache_dir

player = runtime.shell.open_player()
app.processEvents()
check("窗口协调器可打开播放器",
      player is not None and player.isVisible(), type(player).__name__)
check("悬浮层记录主窗口引用",
      runtime.overlay.main_player is player)

runtime.shell.open_settings()
check("窗口协调器可打开设置",
      player.stack.currentWidget() is player.settings_page and player.isVisible(),
      type(player.stack.currentWidget()).__name__)

source = player.now.source
needed_width = (source.fontMetrics().horizontalAdvance(source.text())
                + player.now._SOURCE_TRACKING * max(0, len(source.text()) - 1) + 8)
check("NOW PLAYING 首轮不被裁切", source.width() >= needed_width,
      (source.width(), needed_width))

theme_manager = player._theme_manager
theme = theme_manager.current()
player.now.update_progress(10.0, 100.0, True)
first_icon_key = player.now.b_toggle.icon().cacheKey()
player.now.update_progress(11.0, 100.0, True)
check("播放图标跟随 on_accent 而非硬编码白色",
      player.now._toggle_icon_key == (True, theme.on_accent),
      player.now._toggle_icon_key)
check("同状态 tick 不重建播放图标",
      player.now.b_toggle.icon().cacheKey() == first_icon_key)

settings_panel = player.settings_page.panel
check("嵌入设置页无残留 opacity effect",
      settings_panel.graphicsEffect() is None,
      settings_panel.graphicsEffect())
theme_manager.set_reduce_motion(True)
check("Reduce Motion 下设置面板动画时长为 0",
      settings_panel._fade_duration() == 0, settings_panel._fade_duration())
theme_manager.set_reduce_motion(False)

settings_panel.set_content_accent(QColor("#FF0000"))
check("封面取色不覆盖主题 chrome",
      settings_panel._chrome_accent.name() == theme.accent_fill.lower(),
      (settings_panel._chrome_accent.name(), theme.accent_fill))
check("封面取色进入内容通道",
      settings_panel._content_accent.name() == "#ff0000",
      settings_panel._content_accent.name())
check("封面取色不重写面板 QSS",
      "#ff0000" not in settings_panel.styleSheet().lower())

runtime.shell.show_mini()
app.processEvents()
check("窗口协调器可切回迷你条",
      player is not None and not player.isVisible() and runtime.overlay.isVisible())

if player is not None:
    player._timer.stop()
    player.close()
    app.processEvents()
QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
stored_manager = getattr(runtime.overlay, "theme_manager", None)
check("关闭播放器后主题管理器仍存活",
      isValid(stored_manager),
      "theme_manager=%s" % ("present but deleted" if stored_manager is not None else "missing"))
reopened = runtime.shell.open_player()
app.processEvents()
check("播放器关闭后可再次打开",
      reopened is not None and reopened.isVisible(),
      type(reopened).__name__ if reopened is not None else None)
if reopened is not None:
    check("二次打开复用同一主题管理器",
          reopened._theme_manager is runtime.overlay.theme_manager)
    reopened._timer.stop()
    reopened.close()
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
runtime.overlay._timer.stop()
for timer_name in ("_zorder_timer", "_idle_timer"):
    timer = getattr(runtime.overlay, timer_name, None)
    if timer is not None:
        timer.stop()
try:
    runtime.overlay.hotkeys.unregister()
except Exception:
    pass
runtime.overlay.tray.hide()
runtime.overlay.hide()
runtime.overlay.deleteLater()
app.processEvents()

print("\nRESULT", "PASS" if not FAILS else "FAIL (%d)" % len(FAILS))
if FAILS:
    print("Failed:", ", ".join(FAILS))
sys.exit(0 if not FAILS else 1)
