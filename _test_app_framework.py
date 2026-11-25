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
                   open_player_on_start=False,
                   theme_id="celadon", appearance="light")

_tmp = tempfile.TemporaryDirectory(prefix="desktop-sing-framework-test-")
os.environ["DESKTOP_SING_LISTEN_PATH"] = os.path.join(_tmp.name, "listening.json")

from PySide6.QtCore import (  # noqa: E402
    QCoreApplication,
    QEvent,
    QObject,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QWidget,
)
from shiboken6 import isValid  # noqa: E402

import lyrics_overlay as L  # noqa: E402
import ui_theme as UT  # noqa: E402
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


def _rel_lum(color):
    def channel(value):
        value = value / 255.0
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    return (0.2126 * channel(color.red()) + 0.7152 * channel(color.green())
            + 0.0722 * channel(color.blue()))


def _ratio(first, second):
    high, low = sorted((_rel_lum(first), _rel_lum(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _icon_worst_contrast(icon, background):
    """图标在给定底色上的最低对比度（只看实心像素，跳过抗锯齿边缘）。"""
    image = icon.pixmap(48, 48).toImage()
    worst = 99.0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() < 200:
                continue
            worst = min(worst, _ratio(color, background))
    return worst


def _segmented_selected_contrast(theme):
    """Real pixel contrast between the selected label and its pill."""
    seg = L.Segmented([("a", "AAAA"), ("b", "BBBB")], current="a", h=32)
    seg.set_theme(theme)
    seg.set_accent(QColor(theme.accent_fill))
    seg.resize(260, 32)
    seg.show()
    app.processEvents()
    image = seg.grab().toImage()
    target = QColor(theme.on_accent)
    best = None
    best_distance = 10 ** 9
    for y in range(3, 29):
        for x in range(3, 127):
            pixel = image.pixelColor(x, y)
            distance = (
                (pixel.red() - target.red()) ** 2
                + (pixel.green() - target.green()) ** 2
                + (pixel.blue() - target.blue()) ** 2
            )
            if distance < best_distance:
                best = pixel
                best_distance = distance
    backgrounds = [
        image.pixelColor(x, y)
        for x in (15, 22, 29)
        for y in range(8, 25)
    ]
    ratio = min(_ratio(best, color) for color in backgrounds)
    seg.close()
    seg.deleteLater()
    app.processEvents()
    return ratio


def _slider_focus_probe(theme, value):
    """Render a focused progress slider and sample ring/track/background."""
    host = QWidget()
    host.resize(460, 60)
    host.setObjectName("p1Host")
    host.setStyleSheet(
        "QWidget#p1Host { background: %s; }" % theme.surface_raised
    )
    slider = QSlider(Qt.Horizontal, host)
    slider.setObjectName("progress")
    slider.setRange(0, 1000)
    slider.setValue(value)
    slider.setGeometry(20, 20, 420, 18)
    slider.setStyleSheet(UT.build_qss(theme, "main"))
    slider.setFocusPolicy(Qt.StrongFocus)
    host.show()
    host.activateWindow()
    slider.setFocus(Qt.OtherFocusReason)
    app.processEvents()
    image = host.grab().toImage()
    option = QStyleOptionSlider()
    slider.initStyleOption(option)
    rect = slider.style().subControlRect(
        QStyle.CC_Slider, option, QStyle.SC_SliderHandle, slider
    )
    cx = 20 + rect.center().x()
    cy = 20 + rect.center().y()
    ring = image.pixelColor(cx, 20 + rect.top() + 1)
    track = None
    if value > 0:
        track = image.pixelColor(max(0, 20 + rect.left() - 14), cy)
    background = image.pixelColor(
        min(image.width() - 1, 20 + rect.right() + 14), cy
    )
    result = {
        "focused": slider.hasFocus(),
        "ring": ring,
        "track": track,
        "background": background,
        "ring_track": _ratio(ring, track) if track is not None else None,
        "ring_background": _ratio(ring, background),
    }
    host.close()
    host.deleteLater()
    app.processEvents()
    return result


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

# ---- Theme P1: startup theme + Ctrl+Alt+S standalone panel ----------------
startup_theme = runtime.overlay._current_theme()
check("启动即持有主题管理器（无需主播放器）",
      runtime.overlay.theme_manager is not None
      and startup_theme is not None
      and (startup_theme.id, startup_theme.appearance) == ("celadon", "light"),
      (getattr(startup_theme, "id", None),
       getattr(startup_theme, "appearance", None)))
check("启动阶段确实没有创建主播放器", runtime.overlay.main_player is None)
tray_qss = runtime.overlay._tray_menu.styleSheet().lower()
check("托盘菜单使用 celadon light 语义 token",
      startup_theme.surface_raised.lower() in tray_qss
      and startup_theme.text.lower() in tray_qss
      and "#15181f" not in tray_qss,
      (startup_theme.surface_raised, startup_theme.text))

standalone_returned = runtime.overlay._open_settings(standalone=True)
runtime.overlay._on_hotkey("panel")
app.processEvents()
standalone_panel = runtime.overlay.panel
check("Ctrl+Alt+S 动作创建并显示独立设置面板",
      bool(standalone_returned)
      and standalone_panel is not None
      and standalone_panel.isVisible(),
      (standalone_returned, standalone_panel is not None,
       standalone_panel.isVisible() if standalone_panel is not None else None))
if standalone_panel is not None:
    standalone_panel._fade.stop()
    standalone_panel._clear_fade()
    panel_qss = standalone_panel.styleSheet().lower()
    check("独立设置面板使用 celadon light token",
          startup_theme.bg.lower() in panel_qss
          and "#0c0f15" not in panel_qss,
          startup_theme.bg)
    check("独立设置面板 Segmented 收到完整 theme",
          all(getattr(seg, "_theme", None) is startup_theme
              for seg in standalone_panel._segs))
    standalone_panel._rt.stop()
    standalone_panel.hide()
    standalone_panel.deleteLater()
    runtime.overlay.panel = None
    app.processEvents()

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

light_theme = UT.THEMES["celadon"]["light"]
settings_panel.set_theme(light_theme)
light_qss = settings_panel.styleSheet()
check("浅色主题补上通用滑块样式（不再掉回系统默认蓝）",
      "QSlider::groove:horizontal" in light_qss
      and "#0078d4" not in light_qss.lower())
check("嵌入设置页头部收成与卡片一致的圆角",
      "QWidget#settingsSurface QWidget#head" in light_qss)
icon_bg = QColor(light_theme.surface_raised)
worst = _icon_worst_contrast(settings_panel.b_prev.icon(), icon_bg)
check("上一首图标在浅色卡片上可辨识 (>=3:1)", worst >= 3.0, round(worst, 2))
worst = _icon_worst_contrast(settings_panel.b_saver.icon(), icon_bg)
check("屏保图标在浅色卡片上可辨识 (>=3:1)", worst >= 3.0, round(worst, 2))
on_accent = QColor(light_theme.on_accent)
toggle_img = settings_panel.b_toggle.icon().pixmap(64, 64).toImage()
uses_on_accent = any(
    toggle_img.pixelColor(x, y).alpha() > 200
    and abs(toggle_img.pixelColor(x, y).red() - on_accent.red()) <= 6
    and abs(toggle_img.pixelColor(x, y).green() - on_accent.green()) <= 6
    and abs(toggle_img.pixelColor(x, y).blue() - on_accent.blue()) <= 6
    for y in range(toggle_img.height()) for x in range(toggle_img.width()))
check("设置页播放图标使用主题 on_accent", uses_on_accent, on_accent.name())

probe_seg = L.Segmented([("a", "A"), ("b", "B")])
probe_seg.set_theme(light_theme)
probe_seg.set_accent(QColor(light_theme.accent_fill))
probe_seg.resize(240, 32)
seg_img = probe_seg.grab().toImage()
track_color = seg_img.pixelColor(234, 16)
check("分段控件浅色主题轨道不再是黑槽",
      _rel_lum(track_color) > 0.5, track_color.name())

# ---- Theme P1: Segmented selected label and slider focus contrast --------
for theme_id in ("ink", "celadon"):
    for appearance in ("dark", "light"):
        item = UT.THEMES[theme_id][appearance]
        ratio = _segmented_selected_contrast(item)
        check(f"Segmented {theme_id}/{appearance} 选中文字 >= 4.5:1",
              ratio >= 4.5, round(ratio, 3))
check("负向探针: Segmented 低对比 on_accent 会被拒绝",
      _ratio(QColor("#F15226"),
             QColor(UT.THEMES["ink"]["light"].accent_fill)) < 4.5)

for theme_id in ("ink", "celadon"):
    for appearance in ("dark", "light"):
        item = UT.THEMES[theme_id][appearance]
        expected_ring = item.control_handle_focus.lower()
        for value in (0, 500, 1000):
            result = _slider_focus_probe(item, value)
            label = f"slider {theme_id}/{appearance}/{value}"
            check(f"{label} 焦点态生效", result["focused"])
            check(f"{label} 外环颜色正确",
                  result["ring"].name().lower() == expected_ring,
                  (result["ring"].name(), expected_ring))
            check(f"{label} 焦点环/背景 >= 3.0",
                  result["ring_background"] >= 3.0,
                  round(result["ring_background"], 3))
            if value > 0:
                check(f"{label} 焦点环/filled track >= 3.0",
                      result["ring_track"] >= 3.0,
                      round(result["ring_track"], 3))
check("负向探针: 单色 focus 环在 filled track 上不可靠",
      _ratio(QColor(UT.THEMES["celadon"]["dark"].focus),
             QColor(UT.THEMES["celadon"]["dark"].accent_fill)) < 3.0,
      round(_ratio(QColor(UT.THEMES["celadon"]["dark"].focus),
                   QColor(UT.THEMES["celadon"]["dark"].accent_fill)), 3))
settings_panel.set_theme(theme)

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
