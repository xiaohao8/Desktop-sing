# -*- coding: utf-8 -*-
"""离屏回归烟测（无需真实播放器 / 无需显示器）

覆盖：逐字时间轴、翻译映射、长句自适应字号、5 种样式渲染、
布局尺寸、开关/锁定、悬浮控制条命中、暂停淡出、时间格式、设置面板、
主循环帧驱动、空态渲染。

用法（需已安装 PySide6，且是带 PySide6 的那个 Python）：
    python smoke_test.py

测试期间会临时改写 %APPDATA%\\Desktop-sing\\config.json，
脚本结束会**自动还原**原配置，不会影响你的实际设置。
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import zlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

import _cfg_sandbox

# 干净配置起步：不开全局热键、不拉起保活守护进程、不进空闲屏保。
# 备份按脚本名区分 + atexit/信号兜底还原，见 _cfg_sandbox 模块说明。
_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

fails = []


def check(name, fn):
    try:
        fn()
        print("  ok  -", name)
    except Exception:
        fails.append(name)
        print("  FAIL-", name)
        traceback.print_exc()


import lyrics_overlay as L                                   # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QVariantAnimation, QPropertyAnimation  # noqa: E402
from PySide6.QtGui import QPixmap, QColor                     # noqa: E402


# ---- 给 _pick_session 用的假 SMTC 会话（无需真实播放器）----
import time as _time
import datetime as _dt


class _FakeProps:
    def __init__(self, lut):
        self.last_updated_time = lut


class _FakeSess:
    def __init__(self, src, status, pos, stale):
        self.src = src
        self.age = stale
        self._lut = _dt.datetime.fromtimestamp(_time.time() - stale, tz=_dt.timezone.utc)
        self._status = status
        self._pos = pos

    @property
    def source_app_user_model_id(self):
        return self.src

    def get_playback_info(self):
        class _I:
            pass
        _I.playback_status = self._status
        return _I()

    def get_timeline_properties(self):
        return _FakeProps(self._lut)

    def try_get_media_properties_async(self):
        pass


class _FakeMgr:
    def __init__(self, sessions):
        self._s = sessions

    def get_sessions(self):
        return list(self._s)

app = QApplication(sys.argv)
ov = L.LyricOverlay(L.MediaWatcher())


def _render():
    pm = QPixmap(max(2, ov.width()), max(2, ov.height()))
    pm.fill(Qt.transparent)
    ov.render(pm)


# ---- 伪造一首歌（含逐字、翻译、超长句）----
def fake_song():
    ov.song = {"title": "测试歌曲", "artist": "测试歌手", "album": "",
               "source": "qq", "cover": None}
    ov.lines = [[0.0, "第一句歌词"], [2.0, "第二句歌词"], [5.0, "短句"],
                [8.0, "这是一句极其冗长用于验证长句自适应处理能力是否可靠的歌词内容" * 3],
                [14.0, "末句"]]
    ov.words = {1: [[2.0, 1.0, "第二"], [3.0, 1.0, "句歌词"]]}
    ov.trans = [[0.0, "First line"], [2.0, "Second line"], [5.0, "Short line"],
                [8.0, "Very long translated line for layout stress test"],
                [14.0, "Last line"]]
    ov._trans_map = ov._build_trans_map()
    ov.duration = 200.0
    ov.status = "PLAYING"
    ov.cur_idx = 1
    ov._current_text = ov.lines[1][1]
    ov._next_text = ov.lines[2][1]
    ov._line_t = 1.0
    ov.anchor_pos = 2.4
    ov.anchor_ts = time.monotonic()


print("[1] 逐字时间轴 / 翻译映射")
fake_song()
check("char spans", lambda: ov._char_spans(1, ov.lines[1][1]))
check("trans map 非空", lambda: (_ for _ in ()).throw(AssertionError("empty"))
      if not ov._trans_map else None)
check("trans 命中行1", lambda: (_ for _ in ()).throw(AssertionError(ov._trans_for(1)))
      if ov._trans_for(1) != "Second line" else None)

print("[2] 长句自适应字号")
def _fit():
    f, _fm = ov._fit_font(ov._font_cur, 32, ov.lines[3][1], 300)
    assert f.pixelSize() <= 19, f.pixelSize()
check("fit_font 会缩小", _fit)

print("[3] 5 种样式渲染（翻译 / 时间 / 光晕全开）")
def render_all():
    for style in L.STYLE_NAMES:
        ov.set_style_mode(style)
        ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
        ov._relayout()
        _render()
        assert ov.width() > 40 and ov.height() > 20, (style, ov.width(), ov.height())
check("render all styles", render_all)

print("[4] 布局尺寸：开翻译后应变高")
def size_delta():
    ov.set_style_mode("glass")
    ov.show_trans = False
    ov._relayout()
    h0 = ov.height()
    ov.show_trans = True
    ov._relayout()
    assert ov.height() >= h0, (h0, ov.height())
    for s in ("ios", "spotify", "vinyl"):
        ov.set_style_mode(s)
        ov._relayout()
check("trans 增高", size_delta)

print("[5] 新开关 / 锁定 / 热键")
def toggles():
    ov.set_glow(False); ov.set_glow(True)
    ov.set_show_trans(False); ov.set_show_trans(True)
    ov.set_show_time(False); ov.set_show_time(True)
    ov.set_pause_fade(True)
    ov.set_locked(True)
    assert ov.locked is True
    ov.set_locked(False)
check("toggles", toggles)

def lock_blocks_drag():
    class E:
        def button(self): return Qt.LeftButton
        def position(self): return ov._ctrl_rect().bottomRight() + QPointF(50, 50)
        def globalPosition(self):
            return QPointF(ov.frameGeometry().topLeft() + QPoint(5, 5))
    ov.set_locked(True)
    ov._drag_offset = None
    ov.mousePressEvent(E())
    assert ov._drag_offset is None, "锁定后仍能拖动"
    ov.set_locked(False)
    ov.mousePressEvent(E())
    assert ov._drag_offset is not None, "解锁后无法拖动"
    ov._drag_offset = None
check("锁定阻止拖动", lock_blocks_drag)

print("[6] 悬浮控制条 6 格命中")
def ctrl_hit():
    ov._ctrl_t = 1.0
    r = ov._ctrl_rect()
    assert ov.CTRL_N == 6
    for i in range(ov.CTRL_N):
        assert ov._ctrl_button_at(ov._cell_rect(i, r).center()) == i
    assert ov._ctrl_button_at(r.topLeft() - QPointF(30, 30)) == -1
check("ctrl 6 格", ctrl_hit)

print("[7] 暂停自动淡出")
def pause_fade():
    ov.pause_fade = True
    ov.status = "PAUSED"
    ov._apply_pause_opacity(anim=False)
    assert ov.windowOpacity() < ov.opacity - 0.05, ov.windowOpacity()
    ov.status = "PLAYING"
    ov._apply_pause_opacity(anim=False)
    assert abs(ov.windowOpacity() - ov.opacity) < 0.02
check("暂停淡出", pause_fade)

print("[8] 时间格式")
check("fmt_time", lambda: (_ for _ in ()).throw(AssertionError(ov._fmt_time(200)))
      if ov._fmt_time(200) != "3:20" else None)

print("[9] 设置面板构建 / 换肤 / 刷新")
def panel():
    ov._open_panel()
    p = ov.panel
    assert p is not None
    p.update_accent(QColor("#ff8800"))
    p.refresh()
    for attr in ("hk_check", "trans_check", "glow_check", "lock_check",
                 "pfade_check", "time_check", "ct_check", "cover_check",
                 "keep_check", "saver_check", "saver_idle_check", "auto_check",
                 "dm_seg", "idle_combo", "font_combo", "anim_combo", "style_combo"):
        assert hasattr(p, attr), attr
    assert p.hk_check.isChecked() == ov.hotkeys_on
    # 新旧开关都是同一套接口：isChecked / setChecked / 可 blockSignals
    assert p.keep_check.isChecked() == ov.keepalive
    # 动画样式覆盖 9 种（面板下拉项数 == ANIM_STYLES）
    assert p.anim_combo.count() == len(L.ANIM_STYLES), p.anim_combo.count()
    # 显示模式用分段选择器，值应等于 overlay 当前模式
    assert p.dm_seg.value() == ov.display_mode, p.dm_seg.value()
check("settings panel", panel)

print("[10] 驱动主循环 _on_frame（黑胶 / 光晕 / 切行动画）")
def drive_frames():
    ov.song = {"title": "测试歌曲", "artist": "测试歌手", "source": "qq", "cover": None}
    ov.lines = [[0.0, "甲"], [1.0, "乙"], [2.0, "丙"], [3.0, "丁"]]
    ov.trans = [[1.0, "B-trans"]]
    ov._trans_map = ov._build_trans_map()
    ov.words = {}
    ov.duration = 100.0
    ov.status = "PLAYING"
    ov.anim_style = "slide"
    ov.glow = True
    for style in L.STYLE_NAMES:
        ov.set_style_mode(style)
        for k in range(6):
            ov.anchor_pos = k * 0.5
            ov.anchor_ts = time.monotonic()
            ov._on_frame()
        _render()
check("drive frames", drive_frames)

print("[11] 9 种逐字动画逐帧渲染（含扇形 / 波浪 / 打字机 / 弹跳）")
def all_anims():
    ov.anim_style = "slide"
    for key in L.ANIM_STYLES:
        ov.set_anim_style(key)
        assert ov.anim_style == key, key
        for style in ("glass", "native"):
            ov.set_style_mode(style)
            for frac in (0.0, 0.35, 1.0):        # 入场动画的起/中/末三帧
                ov._line_t = frac
                ov._on_line_anim(frac)
                ov.anchor_pos = 2.0 + frac
                ov.anchor_ts = time.monotonic()
                ov._on_frame()
                _render()
check("all anim styles", all_anims)

print("[12] 空态（无歌）渲染")
def empty_state():
    ov.song = None
    ov.lines, ov.trans, ov._trans_map, ov.cur_idx = [], [], {}, -1
    ov._relayout()
    for style in L.STYLE_NAMES:
        ov.set_style_mode(style)
        _render()
check("empty render", empty_state)

print("[13] 字体库：状态 / 族名匹配 / 下载入口")
def fontlib():
    st = L.font_library_state()
    assert set(st) == {e["id"] for e in L.FONT_LIBRARY}, st
    assert all(isinstance(v, bool) for v in st.values())
    assert L._pick_family(["MiSans Medium", "MiSans Regular"]) == "MiSans Medium"
    assert L._pick_family([]) == ""
    assert L._font_family_match("MiSans Semibold", "misans")
    assert L._font_family_match("LXGW WenKai", "wenkai")
    assert not L._font_family_match("Microsoft YaHei UI", "misans")
    # 每个条目都要有可用的下载地址与文件名（离线也不报错，只是不下载）
    # files 现在是 [(文件名, [url, 镜像1, 镜像2...])]，兼容单 str 旧式
    for e in L.FONT_LIBRARY:
        assert e["files"], e["id"]
        for _n, urls in e["files"]:
            if isinstance(urls, str):
                urls = [urls]
            assert all(u.startswith("http") for u in urls), (e["id"], urls)
    assert L.FONT_MATCH and len(L.FONT_MATCH) == len(L.FONT_LIBRARY)
check("font library", fontlib)


print("[14] 氛围屏保：黑底渲染 / 漂移不越界 / 输入即退")
def saver():
    ov.song = {"title": "测试歌曲", "artist": "测试歌手", "source": "qq", "cover": None}
    ov._current_text, ov._next_text = "夜色温柔", "风也温柔"
    saver_ = L.AmbientSaver(ov)
    saver_.resize(640, 400)
    pm = QPixmap(640, 400)
    pm.fill(Qt.transparent)
    saver_.render(pm)
    img = pm.toImage()
    assert img.pixelColor(2, 2).red() < 40, img.pixelColor(2, 2).red()   # 四角接近纯黑
    # 时钟漂移：不同时刻的绘制不应完全相同，也不该跑出屏幕
    t0 = saver_._t0
    for dt in (0.0, 7.0, 23.0, 61.0):
        saver_._t0 = t0 - dt
        p2 = QPixmap(640, 400)
        p2.fill(Qt.transparent)
        saver_.render(p2)
        assert p2.toImage().pixelColor(320, 200).alpha() >= 0
    got = []
    saver_.finished.connect(lambda: got.append(1))
    saver_.mousePressEvent(type("E", (), {"button": lambda self: Qt.LeftButton})())
    assert got == [1], got
check("ambient saver", saver)


print("[14b] 空闲阈值自动进屏保 → 关闭回环")
def idle_roundtrip():
    saved_idle, saved_locked = L.idle_seconds, L.session_locked
    try:
        ov.idle_saver = False
        ov._check_idle()
        assert ov.saver is None, "未开启自动进入时不该起屏保"
        ov.idle_saver = True
        ov.idle_min = 10
        L.idle_seconds = lambda: 5.0            # 未到阈值
        ov._check_idle()
        assert ov.saver is None, "未到阈值就起了屏保"
        L.idle_seconds = lambda: 601.0          # 超过阈值
        L.session_locked = lambda: True         # 锁屏中：不该起
        ov._check_idle()
        assert ov.saver is None, "锁屏时仍启动了屏保"
        L.session_locked = lambda: False
        ov._check_idle()
        assert ov.saver is not None, "到阈值且未锁屏时应自动进入屏保"
        ov.close_saver()
        assert ov.saver is None, "关闭后 saver 引用未清空"
    finally:
        L.idle_seconds, L.session_locked = saved_idle, saved_locked
        ov.idle_saver = False
        if ov.saver is not None:
            ov.close_saver()
check("idle -> saver", idle_roundtrip)

print("[15] 系统能力：空闲 / 锁屏 / 保活命令 / 菜单皮肤")
def sysstuff():
    assert isinstance(L.idle_seconds(), float) and L.idle_seconds() >= 0
    assert isinstance(L.session_locked(), bool)
    cmd = L._app_command()
    assert isinstance(cmd, list) and len(cmd) >= 1
    sup = L._app_command(supervise=True, watch_pid=12345)
    assert L.SUPERVISE_FLAG in sup, sup
    assert L.WATCH_PID_FLAG in sup and "12345" in sup, sup
    assert isinstance(L.supervisor_alive(), bool)
    assert L.SUPERVISED_ENV and L.SUPERVISOR_PID.endswith("supervisor.pid")
    # 未显式开启保活时不应存在守护进程 pid 文件残留判断错误
    assert L.STOP_SENTINEL.endswith("keepalive.off")
    qss = L.menu_qss(QColor("#22cc88"))
    assert "#22cc88" in qss and "QMenu" in qss
check("system helpers", sysstuff)


print("[16] 开关 / 分段选择器组件")
def widgets():
    hits = []
    sw = L.Switch(False)
    sw.toggled.connect(hits.append)
    sw.setChecked(True, emit=True, animate=False)
    assert sw.isChecked() and hits == [True], (sw.isChecked(), hits)
    on_px = sw.grab().toImage().pixelColor(2, 12)      # 左端：开态应是主色轨道
    sw.setChecked(False, emit=False, animate=False)
    assert not sw.isChecked() and hits == [True]
    off_px = sw.grab().toImage().pixelColor(2, 12)
    # 用 grab() 而非 render()：render(pixmap) 在本环境下画不出任何东西（全透明），
    # 那种"渲染断言"是空转的，抓不到回归。
    assert on_px != off_px, "开关开/关两态没画出区别（%s vs %s）" % (on_px.getRgb(), off_px.getRgb())
    seg_hits = []
    sg = L.Segmented([("a", "甲"), ("b", "乙"), ("c", "丙")], "a")
    sg.changed.connect(seg_hits.append)
    sg.setValue("c", emit=True, animate=False)
    assert sg.value() == "c" and seg_hits == ["c"], (sg.value(), seg_hits)
    sg.resize(240, 32)
    assert sg.grab().toImage().pixelColor(220, 16).alpha() == 255, "分段选择器没画出内容"
check("switch / segmented", widgets)


print("[17] 播放进度锚点连续性（切主题/跳变不抖、不丢同步）")
def anchor_continuity():
    import time as _t
    ov.status = "PLAYING"
    ov.anchor_pos = 10.0
    ov.anchor_ts = _t.monotonic() - 5.0
    ov._last_tick_pos = None
    # 首次 tick：应建立锚点
    ov._apply_tick(15.0, 200.0, "PLAYING")
    assert abs(ov._current_pos() - 15.0) < 0.6, ov._current_pos()
    # 主站抖 0.3s：应被忽略（不重置），歌词/进度继续用本地外推
    ov._apply_tick(15.3, 200.0, "PLAYING")
    assert abs(ov._current_pos() - 15.0) < 0.6, ov._current_pos()
    # 明显跳变（切歌/快进）：应重新锚定
    ov._apply_tick(40.0, 200.0, "PLAYING")
    assert abs(ov._current_pos() - 40.0) < 0.6, ov._current_pos()
    # 暂停：位置冻结
    ov._apply_tick(50.0, 200.0, "PAUSED")
    assert abs(ov._current_pos() - 50.0) < 0.001, ov._current_pos()
check("anchor continuity", anchor_continuity)


print("[17b] 上报冻结免疫：播放器 pos 不动而音乐在放，外推不得被反复拽回")
def frozen_report():
    import time as _t
    ov.status = "PLAYING"
    ov._last_tick_pos = None
    ov._apply_tick(100.0, 200.0, "PLAYING")      # 建立锚点
    # 把锚点拨回 4s 前：外推已在 104，而播放器上报仍冻结在 100
    ov.anchor_ts = _t.monotonic() - 4.0
    for _ in range(3):
        ov._apply_tick(100.0, 200.0, "PLAYING")
    cur = ov._current_pos()
    assert abs(cur - 104.0) < 1.0, "冻结上报期间被拽回: pos=%s" % cur
    # 上报恢复（跟到当前真实位置附近）：应正常跟随
    ov._apply_tick(104.2, 200.0, "PLAYING")
    assert abs(ov._current_pos() - 104.2) < 1.2, ov._current_pos()
    # 大幅回退（拖回 30s）：仍应跟随
    ov._apply_tick(74.0, 200.0, "PLAYING")
    assert abs(ov._current_pos() - 74.0) < 1.2, ov._current_pos()
check("frozen report immunity", frozen_report)


print("[17c] _live_pos 直传（v2.4.12 回退 v2.4.9 外推）：任何输入都原样返回播放器给的 position")
def live_pos_passthrough():
    import datetime as _dt
    now = 1_700_000_000.0
    fresh = _dt.datetime.fromtimestamp(now - 0.3, tz=_dt.timezone.utc)
    stale = _dt.datetime.fromtimestamp(now - 12.0, tz=_dt.timezone.utc)
    # 根因：v2.4.9 在 _live_pos 里按 (now - last_updated_time) 外推，但 QQ音乐/
    # 网易云的 position 已经是最新值、last_updated 才陈旧，外推会重复计数 →
    # 歌词整体跑快、连默认主题都不同步 → 锚点被拽回 8s → 「三秒一跳/卡住」。
    # 现改为一律直传，由 _apply_tick 的锚点外推统一平滑，杜绝双重计数。
    cases = [
        (100.0, stale, "PLAYING"),
        (100.0, fresh, "PLAYING"),
        (100.0, stale, "PAUSED"),
        (100.0, object(), "PLAYING"),   # last_updated 不可解析
        (100.0, 0, "PLAYING"),          # FILETIME=0 脏数据
        (100.0, (now + 30.0 + 11644473600.0) * 10_000_000.0, "PLAYING"),  # 未来时间
        (100.0, (now - 5.0 + 11644473600.0) * 10_000_000.0, "PLAYING"),   # FILETIME 数值
    ]
    for raw, lu, st in cases:
        p = L._live_pos(raw, lu, st, now=now)
        assert p == raw, (raw, lu, st, p)
check("live pos passthrough", live_pos_passthrough)


print("[17d] 幽灵会话规避：_lut_age 与 _pick_session 新鲜度排序")
def ghost_session_pick():
    import datetime as _dt
    z = _dt.timezone.utc
    # 三个假会话：幽灵(PAUSED+极旧)、真在放(PLAYING+新鲜)、同 stale
    ghost = _FakeSess("QQMusic.exe", "PAUSED", 10.0, stale=999.0)
    real = _FakeSess("QQMusic.exe", "PLAYING", 120.0, stale=0.2)
    stale2 = _FakeSess("cloudmusic.exe", "PLAYING", 5.0, stale=50.0)
    mgr = _FakeMgr([ghost, real, stale2])
    chosen = L.MediaWatcher._pick_session(mgr, "")
    assert chosen.src == "QQMusic.exe" and chosen.age == 0.2, (chosen.src, chosen.age)
    # 只有一个幽灵 PAUSED，永远选它（不崩），但 age 标记脏
    only = _FakeSess("QQMusic.exe", "PAUSED", 200.0, stale=1234.0)
    mgr2 = _FakeMgr([only])
    c2 = L.MediaWatcher._pick_session(mgr2, "")
    assert c2 is not None
check("ghost session pick", ghost_session_pick)


print("[18] 字体库国内镜像回退（主站挂 → 落镜像；全挂 → 抛错）")
def mirror_fallback():
    import io, urllib, urllib.request as _ureq, urllib.error as _uerr
    entry = {"id": "t", "name": "测试", "mb": 0.1,
             "files": [("t.ttf", ["https://cdn.jsdelivr.net/x/t.ttf",
                                  "https://ghfast.top/https://github.com/x/t.ttf",
                                  "https://ghproxy.net/https://github.com/x/t.ttf"])]}
    dst = os.path.join(L.USER_FONT_DIR, "t.ttf")
    try:
        calls = []
        class _Resp:
            def __init__(self, d):
                self._d = d
                # 模拟 http.client.HTTPResponse.headers（.get() 接口）
                self.headers = {"Content-Length": None}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n=-1):
                if n == -1: return self._d
                r = self._d[:n]; self._d = self._d[n:]; return r
        class _Opener:
            def __call__(self, req, timeout=90):
                url = req.full_url if hasattr(req, "full_url") else str(req)
                calls.append(url)
                if "jsdelivr" in url:
                    raise _uerr.URLError("sim fail")
                return _Resp(b"\x00\x01")
        orig = _ureq.urlopen
        _ureq.urlopen = _Opener()
        try:
            L.download_font(entry)
        finally:
            _ureq.urlopen = orig
        assert any("ghfast.top" in c or "ghproxy" in c for c in calls), calls
        # 全部失败 → 抛 RuntimeError
        def _fail_all(*a, **k):
            raise _uerr.URLError("boom")
        _ureq.urlopen = _fail_all
        raised = False
        try:
            L.download_font(entry)
        except RuntimeError:
            raised = True
        finally:
            _ureq.urlopen = orig
        assert raised, "全部镜像失败时应抛 RuntimeError"
    finally:
        try:
            os.remove(dst)
        except OSError:
            pass
check("font mirror fallback", mirror_fallback)


print("[19] 屏保四风格渲染（粒子 / 极简 / 音浪 / 星轨，均纯黑底不烧屏）")
def saver_styles():
    ov.song = {"title": "测试歌曲", "artist": "测试歌手", "source": "qq", "cover": None}
    ov._current_text, ov._next_text = "夜色温柔", "风也温柔"
    for style in ("particle", "minimal", "bars", "orbits"):
        ov.saver_style = style
        s = L.AmbientSaver(ov)
        s.resize(640, 400)
        pm = QPixmap(640, 400); pm.fill(Qt.transparent)
        s.render(pm)
        assert pm.toImage().pixelColor(2, 2).red() < 40, (style, pm.toImage().pixelColor(2, 2).red())
        s.finish()
check("saver styles", saver_styles)


print("[19b] 屏保版式门禁：文字不被动画遮挡 / 不越安全边距 / AOD 换位行程不为 0")
def saver_layout():
    """这里只是快子集；全量巡检在 _diag_saver_layout.py（4 风格 × 7 分辨率 ×
    整个换位周期 × 两种行数 + 变异自检）。

    为什么必须有这道门禁：曾经真实漏过一次 —— 4 行版式把文字区填满，
    换位行程只剩 0.1px，换位代码在跑却一点位移都没有，防烧屏悄悄失效，
    而当时所有测试都是绿的。
    """
    ov._current_text, ov._next_text = "夜色温柔", "风也温柔"
    A = L.AmbientSaver
    period = A.ANCHOR_HOLD + A.ANCHOR_MOVE
    for style in ("particle", "minimal", "bars", "orbits"):
        ov.saver_style = style
        for (w, h) in ((1920, 1080), (1280, 960), (252, 142)):
            s = A(ov)
            s.resize(w, h)
            for t in (0.0, A.ANCHOR_HOLD + A.ANCHOR_MOVE * 0.5, period * 2):
                plan = s._plan(w, h, t)
                blk, band = plan["block"], plan["band"]
                sx, sy = w * s.SAFE_X, h * s.SAFE_Y
                assert blk.left() >= sx - 0.5 and blk.right() <= w - sx + 0.5, \
                    "%s %dx%d t=%.0f 文字横向越界 %.1f..%.1f" % (
                        style, w, h, t, blk.left(), blk.right())
                assert blk.top() >= sy - 0.5 and blk.bottom() <= h - sy + 0.5, \
                    "%s %dx%d t=%.0f 文字纵向越界 %.1f..%.1f" % (
                        style, w, h, t, blk.top(), blk.bottom())
                if band is not None:
                    ix = min(band.right(), blk.right()) - max(band.left(), blk.left())
                    iy = min(band.bottom(), blk.bottom()) - max(band.top(), blk.top())
                    assert not (ix > 0.5 and iy > 0.5), \
                        "%s %dx%d t=%.0f 文字块与动画带相交 %.0fx%.0fpx" % (
                            style, w, h, t, ix, iy)
                assert plan["travel"] > 0.05 * plan["tz"].height(), \
                    "%s %dx%d t=%.0f 换位行程仅 %.1fpx（AOD 换位等于没跑）" % (
                        style, w, h, t, plan["travel"])
                if (w, h) == (252, 142):
                    keys = [ln["key"] for ln in plan["lines"]]
                    assert "lyric" in keys, \
                        "%s 面板缩略图丢了歌词行：%s" % (style, keys)
            s.deleteLater()
check("saver layout guard", saver_layout)


print("[20] 屏保风格切换即时生效（面板实时预览 / 托盘单选同步）")
def saver_switch():
    ov.set_saver_style("particle")
    checked = [k for k, a in ov._saver_style_actions.items() if a.isChecked()]
    assert checked == ["particle"], checked
    ov._open_panel()
    p = ov.panel
    assert hasattr(p, "saver_preview"), "面板缺少 saver_preview"
    ov.set_saver_style("bars"); p.refresh()
    pm = p.saver_preview.pixmap()
    assert pm is not None and not pm.isNull(), "切换后预览图为空"
    ov._saver_style_actions["orbits"].trigger()   # 真实走托盘 triggered 路径
    checked = [k for k, a in ov._saver_style_actions.items() if a.isChecked()]
    assert checked == ["orbits"], checked
    assert ov.saver_style == "orbits"
check("saver switch", saver_switch)


print("[21] 逐字时间轴：未覆盖的字必须在本行结束前唱完（不能只亮前几个字就跳行）")
def char_span_bounds():
    ov.lines = [[0.0, "第一句"],
                [3.0, "这是一句很长很长很长很长用于测试省略与逐字高亮的歌词"],
                [12.0, "短句"], [20.0, "末句"]]
    # 逐字数据只覆盖前 16 个字（3.0~7.0s），后面靠兜底展开
    ov.words = {1: [(3.0, 1.0, "这是一句"), (4.0, 1.0, "很长很长"),
                    (5.0, 1.0, "很长很长"), (6.0, 1.0, "用于测试")]}
    ov.cur_idx = 1
    txt = ov.lines[1][1]
    spans = ov._build_char_spans(1, txt)
    line_t1 = ov.lines[2][0]
    assert len(spans) == len(txt), (len(spans), len(txt))
    over = [i for i, (t0, t1) in enumerate(spans) if t0 > line_t1]
    assert not over, "有字排到本行结束(%.1fs)之后、永远点不亮: %s" % (line_t1, over)
    # 无任何逐字数据时，也应平滑铺满整行
    ov.words = {}
    sp2 = ov._build_char_spans(1, txt)
    over2 = [i for i, (t0, t1) in enumerate(sp2) if t0 > line_t1]
    assert not over2, over2
    assert sp2[0][0] >= 3.0 - 1e-6 and sp2[-1][1] <= line_t1 + 1e-6, (sp2[0], sp2[-1])
    # 极端：逐字数据只覆盖前 4 个字、且结束得很晚（5.5s），行尾 6.0s。
    # 旧逻辑从 5.5s 再摊 spread 秒会把其余字全排到行外 -> 只亮前几个字就跳行。
    ov.lines = [[0.0, "A"], [3.0, "甲乙丙丁戊己庚辛壬癸"], [6.0, "B"]]
    ov.words = {1: [(3.0, 1.0, "甲"), (4.0, 1.0, "乙"), (5.0, 0.5, "丙丁")]}
    ov.cur_idx = 1
    txt3 = ov.lines[1][1]
    sp3 = ov._build_char_spans(1, txt3)
    assert len(sp3) == len(txt3)
    over3 = [i for i, (t0, t1) in enumerate(sp3) if t0 > 6.0]
    assert not over3, "极端用例仍有字排到行外: %s" % over3
    assert all(t1 <= 6.0 + 1e-6 for (t0, t1) in sp3), sp3
check("char span bounds", char_span_bounds)


print("[22] 升级接管：restart.sig 写入后旧实例应退出让位（删哨兵 + 写停机哨兵）")
def takeover():
    sig, sent = L.RESTART_SIG, L.STOP_SENTINEL
    had_sig, had_sent = os.path.exists(sig), os.path.exists(sent)
    if had_sig:
        shutil.copy2(sig, sig + ".tbak")
    if had_sent:
        shutil.copy2(sent, sent + ".tbak")
    try:
        # _quit() 只在「确实有守护进程」时才写停机哨兵（没守护进程就无需停机）。
        # 这里显式开启保活，避免测试受本机是否残留守护进程影响。
        prev_keep = ov.keepalive
        ov.keepalive = True
        with open(sig, "w", encoding="utf-8") as f:
            f.write("ver=9.9.9\npid=0\nts=1")
        for _ in range(16):          # _sig_tick 每 15 帧查一次
            ov._on_frame()
        ov.keepalive = prev_keep
        assert not os.path.exists(sig), "接管哨兵未被消费"
        assert os.path.exists(sent), "退出让位时未写停机哨兵（守护进程会复活旧实例）"
    finally:
        ov.keepalive = prev_keep
        if os.path.exists(sig):
            os.remove(sig)
        if had_sig:
            shutil.copy2(sig + ".tbak", sig)
            os.remove(sig + ".tbak")
        if had_sent:
            shutil.copy2(sent + ".tbak", sent)
            os.remove(sent + ".tbak")
        elif os.path.exists(sent):
            os.remove(sent)
check("takeover signal", takeover)


print("[23] 歌词格式识别 / 时间轴工具 / 酷狗 KRC（借鉴 Lyricify-Lyrics-Helper）")
def lyric_formats():
    plain = ("[ti:测试]\n[offset:0]\n"
             "[0,2000]<0,500,0>你<500,500,0>好<1000,500,0>吗\n"
             "[2000,1500]<0,500,0>我<500,500,0>很<1000,500,0>好")
    # KRC 解密往返：复刻算法（zlib 压缩 -> 逐字节异或 -> 前面补 4 字节头 -> base64）
    buf = bytearray(zlib.compress(("\x00" + plain).encode("utf-8")))
    for i in range(len(buf)):
        buf[i] ^= L._KRC_XOR_KEY[i % len(L._KRC_XOR_KEY)]
    enc = base64.b64encode(b"krc1" + bytes(buf)).decode("ascii")
    assert L.decrypt_krc(enc).strip() == plain.strip(), L.decrypt_krc(enc)

    lines, words, trans = L.parse_krc(L.decrypt_krc(enc))
    assert len(lines) == 2 and len(words) == 2, (len(lines), len(words))
    assert abs(lines[0][0]) < 1e-6 and lines[0][1] == "你好吗", lines[0]
    assert abs(words[1][0][0] - 2.0) < 1e-6, words[1][0]        # 逐字是绝对时间
    assert [c[0] for c in words[1]] == sorted(c[0] for c in words[1]), words[1]

    # 格式自动识别 + 自动分发解析
    assert L.detect_lyric_format(plain) == "krc"
    assert L.detect_lyric_format("[00:12.30]你好") == "lrc"
    assert L.detect_lyric_format("[1234,567](0,500,0)你好") == "yrc"
    assert L.detect_lyric_format("没有时间轴的纯文本") == "unsynced"
    al, aw, _at = L.parse_lyrics_auto(plain)
    assert len(al) == len(lines) and len(aw) == len(words)

    # 信息行（歌手 - 歌名 / 版权声明）要剔掉，真歌词要留住
    assert L.is_info_line("买辣椒也用券 - 起风了 (旧版)")
    assert L.is_info_line("（未经著作人许可，不得翻唱、翻录或使用）")
    assert not L.is_info_line("这一路上走走停停")

    # 时间轴偏移 / 逐字降级 / LRC 导出往返
    ol, ow, _ot = L.offset_lines(lines, words, trans, 0.5)
    assert abs(ol[1][0] - lines[1][0] - 0.5) < 1e-6
    assert abs(ow[0][0][0] - words[0][0][0] - 0.5) < 1e-6
    dl, dw, _dt = L.downgrade_to_lines(lines, trans)
    assert dw == {} and len(dl) == len(lines)
    back, _bw = L.parse_lrc(L.generate_lrc(lines))
    assert len(back) == len(lines) and back[0][1] == lines[0][1], back[:2]
check("lyric formats / krc / tools", lyric_formats)

print("[24] 歌词质量评分 / 清洗 / 繁简转换（借鉴 Lyricify 智能匹配引擎 + Lyrics Optimization）")
def lyric_quality():
    # 评分：普通 < 带逐字 < 满配（逐字+翻译）；空结果 -1；串词（末行远超时长）要更低
    plain = [[float(i * 5), "第%d句" % i] for i in range(30)]
    bare = L.score_lyrics(plain, None, None, 155.0)
    worded = L.score_lyrics(plain, {0: [[0.0, 1.0, "第"]]}, None, 155.0)
    full = L.score_lyrics(plain, {0: [[0.0, 1.0, "第"]]}, [[0.0, "t"]], 155.0)
    assert 0 < bare < worded < full, (bare, worded, full)
    assert L.score_lyrics([]) == -1
    assert L.score_lyrics([[0.0, "a"], [900.0, "b"]], None, None, 200.0) < bare
    # 末行贴合歌曲全长时应当加满分
    tight = L.score_lyrics([[0.0, "a"], [154.0, "b"]] + plain[2:], None, None, 155.0)
    assert tight > L.score_lyrics([[0.0, "a"], [500.0, "b"]] + plain[2:], None, None, 155.0)

    # 清洗：信息行 / 空行 / 纯符号行丢掉，同时间戳去重，words 行号要跟着重建
    raw = [[0.0, "买辣椒也用券 - 起风了"],
           [1.0, "未经许可不得翻唱或使用"],
           [10.0, "这一路上走走停停"],
           [10.0, "这一路上走走停停"],
           [13.0, ""],
           [16.0, "..."],
           [20.0, "顺着少年漂流的痕迹"]]
    rw = {2: [[10.0, 0.3, "这"], [10.3, 0.3, "一"]],
          3: [[10.0, 0.3, "x"]],
          6: [[20.0, 0.4, "顺"]]}
    rt = [[10.0, "这一路上走走停停"], [10.0, ""], [21.0, "沿着少年漂流的痕迹"]]
    cl, cw, ct = L.clean_lyrics(raw, rw, rt)
    assert cl == [[10.0, "这一路上走走停停"], [20.0, "顺着少年漂流的痕迹"]], cl
    assert list(cw) == [0, 1], cw                    # 旧 3 号行被同时间戳去重丢掉
    assert cw[0][0][2] == "这" and cw[1][0][2] == "顺", cw
    assert ct == [[10.0, "这一路上走走停停"], [21.0, "沿着少年漂流的痕迹"]], ct
    assert L.clean_lyrics([], {}, []) == ([], {}, [])

    # 繁简转换：字表必须两两成对，且不允许"一字两简"的冲突映射
    toks = L.T2S_PARTIAL.split()
    assert toks and all(len(t) == 2 for t in toks), [t for t in toks if len(t) != 2]
    table = L._load_t2s()
    assert len(table) > 500, len(table)
    seen = {}
    for k, v in table.items():
        assert seen.setdefault(k, v) == v, (k, seen[k], v)
    assert L.to_simplified("我們說對不起，時間會證明一切") == "我们说对不起，时间会证明一切"
    assert L.to_simplified("风里的花") == "风里的花"      # 简体原样返回
    assert L.to_simplified("") == ""
    assert L.to_simplified("龘", {}) == "龘"             # 未收录字符不猜，原样保留

    # 制作名单 / 致谢行必须剔掉，正常歌词一个字都不能误伤（冒号是安全阀）
    for s in ("作词：李荣浩", "曲：周杰伦", "编曲 Arrangement：陈伟", "小提琴：须磨和声",
              "母带工程师：Chris", "录音工程：玉乃井光纪", "特别支持：中村光雄",
              "音乐总监：陈伟", "联合出品：腾讯音乐", "混音师：李军", "贝斯"):
        assert L.is_info_line(s), "应判为制作名单却漏了: " + s
    for s in ("鼓起勇气", "曲终人散", "设计好的结局", "录音机里放着老歌", "作曲家的心事",
              "感谢你曾经来过", "特别支持我的人", "指挥着我的心跳", "written in the stars",
              "这一路上走走停停"):
        assert not L.is_info_line(s), "正常歌词被误判: " + s
check("lyric quality / clean / t2s", lyric_quality)

print("[25] 摆放位置预设（借鉴 FluentFlyout 的可定制浮层位置）")
def position_presets():
    from PySide6.QtWidgets import QMenu          # noqa: F401
    g = QApplication.primaryScreen().availableGeometry()
    m = L.POSITION_MARGIN
    ov.resize(600, 200)
    w, h = ov.width(), ov.height()

    # 每个预设都要落在屏幕安全区内、互不重合，且窗口真的挪过去了
    seen = set()
    for key, _name in L.POSITION_PRESETS:
        ov._apply_position_preset(key)
        x, y = ov._preset_point(key)
        assert g.x() <= x and x + w <= g.x() + g.width(), (key, x, g.x(), g.width())
        assert g.y() <= y and y + h <= g.y() + g.height(), (key, y, g.y(), g.height())
        assert (x, y) not in seen, "预设位置重合: " + key
        seen.add((x, y))
        assert (ov.pos().x(), ov.pos().y()) == (x, y), key
        assert ov._current_position_key() == key, (key, ov._current_position_key())
        assert ov.pos_preset == key

    # 贴边预设必须真的贴边（好分辨率/任务栏高度变化也跟着走）
    assert ov._preset_point("top")[1] == g.y() + m
    assert ov._preset_point("bottom")[1] + h == g.y() + g.height() - m
    assert ov._preset_point("top_left")[0] == g.x() + m
    assert ov._preset_point("top_right")[0] + w == g.x() + g.width() - m

    # 手动挪走后应判为"自由摆放"，且不再被预设接管
    ov.move(ov.pos().x() + 37, ov.pos().y() - 19)
    assert ov._current_position_key() == L.POS_FREE, ov._current_position_key()
    ov._set_pos_free()
    assert ov.pos_preset == L.POS_FREE and ov.cfg.get("pos_preset") == L.POS_FREE

    # 重启还原：配了预设就按当前屏幕重算，没配就回到记忆坐标
    ov.cfg["pos_preset"] = "top_right"
    ov._restore_position()
    assert ov._current_position_key() == "top_right"
    ov.cfg.pop("pos_preset", None)
    ov.cfg["x"], ov.cfg["y"] = g.x() + 11, g.y() + 22
    ov._restore_position()
    assert (ov.pos().x(), ov.pos().y()) == (g.x() + 11, g.y() + 22)

    # 菜单要真的建得出来，当前项有勾
    menu = QMenu()
    sub = ov._build_pos_menu(menu, track=True)
    assert sub is not None and sub.title() == "摆放位置", sub
    assert any(a.isCheckable() and a.isChecked() for a in sub.actions()), "无勾选项"
    assert len(ov._pos_actions) == len(L.POSITION_PRESETS)
    ov._sync_tray_menu()
check("position presets", position_presets)


print("[26] 多源并行抓词：快源先到即用、慢源不得拖链路（打桩，不走网络）")
def parallel_fetch():
    real = L._fetch_source

    def mk(lines_n, words_n, trans_n):
        lines = [[i * 3.0, "第%d句" % i] for i in range(lines_n)]
        words = {i: [[i * 3.0, 0.5, "字"]] for i in range(words_n)}
        trans = [[i * 3.0, "t%d" % i] for i in range(trans_n)]
        return {"lines": lines, "words": words, "trans": trans, "cover": None}

    def run(plan, budget_note=""):
        """plan: {源: (延迟秒, 候选或 None)}；返回 (耗时, lines, words, trans, used, by_src)"""
        def fake(src, query, tc, ac):
            delay, cand = plan.get(src, (0.0, None))
            if delay:
                time.sleep(delay)
            return cand
        L._fetch_source = fake
        try:
            t0 = time.perf_counter()
            lines, words, trans, cover, used, by_src = L._gather_sources(
                "q", "t", "a", 200.0, False)
            return time.perf_counter() - t0, lines, words, trans, used, by_src
        finally:
            L._fetch_source = real

    try:
        # 1) 慢源（LRCLIB 2.2s）绝不能挡住链路：国内源已给满配 → 必须立刻收工
        dt, lines, words, trans, used, _ = run({
            "qq": (0.03, mk(40, 40, 40)),
            "netease": (0.05, mk(38, 0, 0)),
            "kugou": (0.04, mk(39, 39, 39)),
            "lrclib": (2.2, mk(50, 0, 0)),
        })
        assert dt < 0.8, "慢源把链路拖住了: %.2fs" % dt
        assert words and trans, (len(words), len(trans))
        assert used in ("qq", "kugou"), used

        # 2) 满配后的小宽限期要生效：稍慢但逐字更全的同级源应能翻盘
        dt, lines, words, trans, used, _ = run({
            "qq": (0.02, mk(30, 30, 30)),         # 先到，逐字覆盖少
            "netease": (0.12, mk(45, 45, 45)),    # 慢 100ms，但明显更全
            "kugou": (0.05, mk(20, 20, 20)),
            "lrclib": (0.0, None),
        })
        assert used == "netease", "没让更优的同级结果翻盘: " + str(used)
        assert len(lines) == 45 and len(words) == 45
        assert dt < 0.8, dt

        # 3) 两个满配源、其中一个很慢：必须在宽限期后就走，不等慢的那个
        dt, _l, _w, _t, _u, _b = run({
            "qq": (0.03, mk(30, 30, 30)),
            "netease": (1.5, mk(60, 60, 60)),
            "kugou": (0.0, None),
            "lrclib": (0.0, None),
        })
        assert dt < 0.8, "等了慢源: %.2fs" % dt

        # 4) 缺逐字时才等 LRCLIB 兜底，且总耗时卡死在预算内
        dt, lines, words, trans, used, _ = run({
            "qq": (0.03, mk(30, 0, 0)),
            "netease": (0.05, None),
            "kugou": (0.04, None),
            "lrclib": (0.6, mk(30, 30, 0)),
        })
        assert used == "lrclib" and words, (used, len(words))
        assert dt < 1.5, dt

        # 5) 已有正文时，不带逐字的 LRCLIB 候选应被忽略（别用更差的覆盖好的）
        dt, lines, words, trans, used, _ = run({
            "qq": (0.03, mk(30, 0, 0)),
            "netease": (0.05, None),
            "kugou": (0.04, None),
            "lrclib": (0.2, mk(45, 0, 0)),        # 行更多但没逐字
        })
        assert used == "qq", "被无逐字的 LRCLIB 覆盖了: " + str(used)
        assert len(lines) == 30
    finally:
        L._fetch_source = real
check("parallel fetch", parallel_fetch)


print("[27] 省电：隐藏即停帧、静止不空转重绘")
def idle_power():
    from PySide6.QtCore import QVariantAnimation
    ov.show()
    ov.song = {"title": "t", "artist": "a", "source": "qq", "cover": None}
    ov.lines = [[i * 3.0, "第%d句" % i] for i in range(20)]
    ov.words = {}
    ov.status = "PLAYING"

    # 播放：必须持续重绘
    assert ov._needs_repaint() is True
    ov._on_frame()
    assert ov._timer.interval() == 33, ov._timer.interval()

    # 暂停且无动画：不该再重绘，定时器降到巡检频率
    ov.status = "PAUSED"
    ov._line_anim.stop()
    ov._size_anim.stop()
    ov._pause_anim.stop()
    ov._ctrl_anim.stop()
    assert ov._needs_repaint() is False
    for _ in range(3):
        ov._on_frame()
    assert ov._timer.interval() == 250, ov._timer.interval()
    assert ov._last_frame_pos == ov._lyric_pos()

    # 等待态有呼吸动画：仍要重绘
    ov.song = None
    assert ov._needs_repaint() is True
    ov._on_frame()

    # 隐藏：定时器整条停掉；重新可见要能自己恢复
    ov.hide()
    assert ov._timer.isActive() is False, "隐藏后帧定时器还在跑"
    ov.show()
    assert ov._timer.isActive() is True, "重新显示后帧定时器没恢复"
check("idle power", idle_power)


print("[28] UI 美化：柔和描边 / 下拉箭头 / 圆角裁图 / 分段轨道对比度")
def ui_polish():
    from PySide6.QtGui import QPainter, QFont, QFontMetrics

    # ---- 描边必须两层，且「外宽内窄、外淡内深」----
    pens = L.LyricOverlay._halo_pens(ov, 3.4)
    assert len(pens) == 2, "柔和描边应为两层，实际 %d" % len(pens)
    outer, inner = pens
    assert outer.width() > inner.width(), (outer.width(), inner.width())
    assert outer.color().alpha() < inner.color().alpha(), \
        "外圈必须比内圈淡（外圈负责柔和过渡，内圈负责边缘清晰度）"
    assert L.LyricOverlay._halo_pens(ov, 0) == (), "halo_w<=0 时不应产生描边"

    # ---- 描边真的铺到了字外：同一个字，带描边的墨迹必须更多 ----
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(26)
    fm = QFontMetrics(f)

    def ink(with_halo):
        pm = QPixmap(120, 48)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        ov._draw_plain(p, "国", 12, 36, f, fm, 3.4, 255, halo_on=with_halo)
        p.end()
        img = pm.toImage()
        n = 0
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                if img.pixelColor(x, y).alpha() > 8:
                    n += 1
        return n

    a, b = ink(True), ink(False)
    assert a > b, "柔和描边没铺到字外（带描边 %d vs 纯填充 %d）" % (a, b)

    # ---- 圆角裁图：四角必须透明，中心必须保留 ----
    src = QPixmap(40, 40)
    src.fill(QColor(255, 0, 0))
    rp = L.round_pixmap(src, 12)
    ri = rp.toImage()
    assert ri.pixelColor(0, 0).alpha() == 0, "圆角外应透明（QLabel 的 border-radius 不裁子图）"
    assert ri.pixelColor(20, 20).alpha() > 200, "中心不该被裁掉"

    # ---- 下拉箭头：必须落到一张真实存在的图，且不能再出现 CSS 三角写法 ----
    url = L.combo_arrow_url()
    assert url, "下拉箭头图未生成"
    assert os.path.exists(url.replace("/", os.sep)), "箭头图路径不存在：%s" % url

    # ---- 分段选择器轨道必须明显比卡片底更深，否则控件会「飘」在卡片上 ----
    # 注意用 grab() 而不是 render()：本环境下 QWidget.render(pixmap) 画不出任何东西
    # （全透明），grab() 才真的走一遍 paintEvent。早先测试 [16] 里的 render() 就是空转。
    seg = L.Segmented([("a", "甲"), ("b", "乙")], "a", h=30)
    seg.resize(200, 30)
    simg = seg.grab().toImage()

    def lum(c):
        return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()

    track = simg.pixelColor(180, 15)               # 右半段未选中，露出的应是轨道
    pill = simg.pixelColor(60, 15)                 # 左半段是选中滑块（主色）
    card_deep = QColor("#14171e")                  # 卡片渐变的最深处
    assert track.alpha() == 255, "轨道没画出来（采样全透明说明 grab 失败）"
    assert lum(track) < lum(card_deep) - 4, \
        "分段轨道不够深，会糊在卡片里（轨道 %.1f vs 卡片 %.1f）" % (lum(track), lum(card_deep))
    assert lum(pill) > lum(card_deep) + 20, "选中滑块没画出来（采样 %.1f）" % lum(pill)

    # ---- 面板：屏保按钮已从「通栏高饱和主色」降级为描边式，箭头也不再是方块 ----
    ov._open_panel()
    p = ov.panel
    sv = [b for b in p.findChildren(L.QPushButton) if b.objectName() == "saver"]
    assert len(sv) == 1, "屏保按钮应恰好一个，实际 %d 个（%s）" \
        % (len(sv), [b.objectName() for b in p.findChildren(L.QPushButton)])
    assert sv[0].text() == "立即进入屏保"
    qss = p.styleSheet()
    assert "QPushButton#saver" in qss
    assert "border-left: 4px solid transparent" not in qss, \
        "Qt 的 QSS 不支持 CSS 三角写法（会渲染成方块），不该再出现"
    assert "image: url(" in qss, "下拉箭头应引用真实图片"
check("ui polish", ui_polish)


print("[29] 菜单 / 弹层皮肤：右键菜单、托盘菜单、下拉弹层、对话框都不能漏成原生白底")
def popup_skin():
    from PySide6.QtWidgets import QMenu, QComboBox, QMessageBox

    DARK = "#15181f"

    def is_skinned(m):
        """同一个判据在断言和变异自检里复用，避免"检测逻辑本身失效"。"""
        return DARK in (m.styleSheet() or "")

    # ---- 右键菜单必须套深色皮肤 ----
    # 历史 bug：_show_menu 里漏了 setStyleSheet，于是弹出的是系统原生白底菜单，
    # 和整套深色 UI 直接打架。拆出 _build_context_menu 就是为了这里能拿到对象断言。
    menu = ov._build_context_menu()
    assert menu.styleSheet(), "右键菜单没套任何样式表，会退化成系统原生白底菜单"
    assert is_skinned(menu), "右键菜单底色不是统一深色（%r）" % menu.styleSheet()[:40]
    mq = menu.styleSheet()
    assert "font-family" in mq, \
        "菜单缺 font-family：菜单是顶层弹出窗口，不继承面板 QSS，中文会渲染成方框"
    assert "border-radius: 10px" in mq, "菜单圆角丢了"
    # 子菜单会继承父菜单的样式表，仍要存在
    subs = [a.menu() for a in menu.actions() if a.menu() is not None]
    assert subs, "右键菜单应当有子菜单（样式 / 显示模式 / 悬浮窗 / 摆放位置）"
    texts = [a.text() for a in menu.actions()]
    assert "退出" in texts, "右键菜单缺「退出」项：%s" % texts

    # ---- 子菜单箭头 / 勾选标记必须落到真实图片 ----
    # Qt 的 QSS 画不出 CSS 三角（会渲染成小方块），只能换 PNG。
    for kind in ("menu_arrow", "menu_check"):
        u = L.ui_icon_url(kind)
        assert u, "%s 图标未生成" % kind
        assert os.path.exists(u.replace("/", os.sep)), "%s 路径不存在：%s" % (kind, u)

    # ---- 托盘菜单同样要套皮肤（托盘不一定建起来，在则校验）----
    tray_menu = getattr(ov, "_tray_menu", None)
    if tray_menu is not None:
        assert is_skinned(tray_menu), "托盘菜单没套皮肤"

    # ---- 设置面板里的下拉框：弹层容器必须去掉白边 ----
    # QComboBox 的下拉是个 Qt 私有 QFrame 子类 QComboBoxPrivateContainer，
    # 深色 view 外面包着一圈白边；只有类名选择器能命中它（.QFrame 匹配不到）。
    ov._open_panel()
    combos = ov.panel.findChildren(QComboBox)
    assert combos, "设置面板里应当有下拉框"
    for cb in combos:
        L.fix_combo_popup(cb)
        view = cb.view()
        pop = view.window() if view is not None else None
        if pop is not None and pop is not cb:
            css = pop.styleSheet()
            assert "QComboBoxPrivateContainer" in css, \
                "下拉弹层白边只能用类名选择器去掉（.QFrame 命中不了这个私有子类）"
            assert "border: none" in css, "下拉弹层仍留着白边"

    # ---- 对话框不能再用 QMessageBox.about/warning 的原生白底 ----
    box = L.build_message_box(None, "关于 桌面歌词", "桌面歌词 v%s" % L.APP_VERSION,
                              "测试信息", accent=ov.accent1)
    assert isinstance(box, QMessageBox)
    bq = box.styleSheet()
    assert DARK in bq, "对话框没套深色皮肤（原生 QMessageBox.about 是白底）"
    assert "QMessageBox QPushButton" in bq, "对话框按钮没跟着皮肤走"
    box.deleteLater()

    # ---- 变异自检：判据必须真能分辨「套了皮」和「没套皮」 ----
    assert is_skinned(menu) is True
    bare = QMenu(ov)
    bare.addAction("x")
    assert is_skinned(bare) is False, "空菜单竟被判为已套皮肤——上面的断言本身失效"
    bare.deleteLater()
    menu.deleteLater()
check("popup skin", popup_skin)

print("[30] UI 质感：卡拉OK柔性波前 / 质感令牌一致 / 无占位符残留")
def ui_texture():
    from PySide6.QtGui import QFont, QFontMetrics, QPainter, QIcon

    # ---- karaoke_color：端点、夹取、单调 ----
    ac = QColor("#ff5c8a")
    c0 = L.karaoke_color(ac, 0.0, 108)
    c1 = L.karaoke_color(ac, 1.0, 108)
    assert (c0.red(), c0.green(), c0.blue()) == (255, 255, 255), "t=0 应是白（未唱）"
    assert c0.alpha() == 108, c0.alpha()
    assert (c1.red(), c1.green(), c1.blue()) == (ac.red(), ac.green(), ac.blue()), \
        "t=1 应是封面主色"
    assert c1.alpha() == 252, c1.alpha()
    assert L.karaoke_color(ac, -5, 108).alpha() == 108, "t<0 必须夹到 0"
    assert L.karaoke_color(ac, 9, 108).alpha() == 252, "t>1 必须夹到 1"
    alphas = [L.karaoke_color(ac, t / 10.0, 108).alpha() for t in range(11)]
    assert alphas == sorted(alphas), "透明度必须随 t 单调递增：%s" % alphas

    # ---- 柔性波前：正在唱的那个字必须真的画出横向渐变 ----
    # 判据用「字内左半 / 右半的墨色是否不同」——关掉 soft edge 时整字平色，两侧应几乎一样；
    # 打开时沿字宽铺渐变，靠近"已唱"的一侧必须明显更偏主色。
    ov.set_style_mode("native")
    ov.song = {"title": "t", "artist": "a", "source": "qq", "cover": None}
    ov.cover_pix = None
    ov.accent1, ov.accent2 = ac, QColor("#ffa24a")
    ov.bg_color = L.pill_bg_color(ac)
    ov.offset = 0.0
    TEXT = "唱过一段未唱的字"
    ov.lines = [[0.0, TEXT], [8.0, "下一句"]]
    ov.words = {0: [[float(i), 1.0, ch] for i, ch in enumerate(TEXT)]}
    ov.trans, ov._trans_map = [], {}
    ov.duration = 60.0
    ov._current_text, ov._next_text = TEXT, "下一句"
    ov.cur_idx, ov.status = 0, "PLAYING"
    ov._line_t = 1.0
    ov.glow = ov.show_trans = ov.show_time = ov.show_cover = False
    ov.edge_fade = False
    ov._current_pos = lambda: 4.5              # 下标 4 的字正好唱到一半

    f = ov._font_cur(ov._px(30))
    fm = QFontMetrics(f)
    x0 = 10.0
    cs = fm.horizontalAdvance(TEXT[:4])        # 前 4 字占宽 → 活动字起点
    cw = fm.horizontalAdvance(TEXT[4])

    def green_profile(soft):
        """返回活动字左 25% / 右 25% 两处的代表墨色绿通道值。

        主色 #ff5c8a 的绿通道(92)远低于未唱的白(255)，所以"越偏主色 → 绿通道越小"。
        """
        L.KARAOKE_SOFT_EDGE = soft
        pm = QPixmap(700, 70)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        ov._draw_karaoke(p, TEXT, x0, 50, f, fm, 0, 0.0, halo_on=False)
        p.end()
        img = pm.toImage()

        def sample(frac):
            x = int(x0 + cs + cw * frac)
            best, bg = None, 999
            for y in range(img.height()):
                c = img.pixelColor(x, y)
                if c.alpha() > 40 and c.green() < bg:   # 取该列最"实"的像素
                    bg, best = c.green(), c
            return best.green() if best is not None else None

        return sample(0.18), sample(0.82)

    gl_s, gr_s = green_profile(True)
    gl_f, gr_f = green_profile(False)
    L.KARAOKE_SOFT_EDGE = True

    assert gl_s is not None and gr_s is not None, "活动字没画出来（取样全空）"
    assert gl_s < gr_s - 15, \
        "柔性波前没生效：活动字左右两侧应明显不同（左 %s vs 右 %s）" % (gl_s, gr_s)
    assert abs(gl_f - gr_f) <= 6, \
        "关掉 soft edge 后整字应是平色（左 %s vs 右 %s）——这条正是上一条的对照" % (gl_f, gr_f)

    # ---- 质感令牌：面板 QSS 必须真的引用了令牌，且不能有占位符残留 ----
    ov._open_panel()
    qss = ov.panel.styleSheet()
    assert ("border-radius: %dpx" % L.UI_R_CARD) in qss, "卡片圆角没走 UI_R_CARD 令牌"
    assert L.UI_GROOVE in qss, "凹槽底色没走 UI_GROOVE 令牌"
    for ph in ("__A__", "__AL__", "__R_CARD__", "__R_CTRL__", "__R_ICON__",
               "__HI__", "__LO__", "__MID__", "__ARROW__", "__CARD_TOP__",
               "__CARD_BODY__", "__CARD_BOT__", "__CTRL_TOP__", "__CTRL_BOT__",
               "__GROOVE__"):
        assert ph not in qss, "面板 QSS 残留占位符 %s —— 面板会整块掉样式" % ph

    # ---- 菜单项图标：选中态必须换深色（否则浅灰图标压在主色高亮上会糊） ----
    ic = L.make_menu_icon("gear")
    nrm = ic.pixmap(32, 32, QIcon.Mode.Normal)
    sel = ic.pixmap(32, 32, QIcon.Mode.Selected)
    assert not nrm.isNull() and not sel.isNull(), "菜单图标没生成"

    def mean_lum(pm):
        img = pm.toImage()
        tot = cnt = 0
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if c.alpha() > 40:
                    tot += 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
                    cnt += 1
        return (tot / cnt) if cnt else 0.0

    assert mean_lum(sel) < mean_lum(nrm) - 40, \
        "菜单图标的 Selected 态必须是深色（普通 %0.f / 选中 %0.f）" % (mean_lum(nrm), mean_lum(sel))

    del ov._current_pos
check("ui texture", ui_texture)


# ---------------------------------------------------------------------------
print("[31] 配置沙箱：巡检临时改写配置后必须可靠还原")
# ---------------------------------------------------------------------------


def cfg_sandbox():
    """`_cfg_sandbox` 的隔离自测（全部在临时目录里跑，不碰真实配置）。

    这一组守的是「巡检脚本把用户配置搞坏 / 搞丢」这一类事故，具体包括：
    备份路径必须按脚本名区分（旧版三个脚本共用一条路径，并行时互相删备份）、
    往返还原要一字不差、备份被删时不许崩（旧版正是在这里 FileNotFoundError，
    真实断言全过却以退出码 1 收场）、原本没有配置时不许留下临时桩、
    残留锁按 pid 存活立刻抢占（而不是白等整个 timeout）、读不出 pid 时退回 mtime 判定、
    真有人在跑则等满超时而不是硬闯。
    """
    import _cfg_sandbox as cs
    tmp = tempfile.mkdtemp(prefix="cfgbox_")
    saved_paths = (cs.CFG, cs.LOCK, cs.LEGACY_BAK)
    saved_state = dict(cs._state)
    cs.CFG = os.path.join(tmp, "config.json")
    cs.LOCK = cs.CFG + ".sandbox.lock"
    cs.LEGACY_BAK = cs.CFG + ".prevbak"
    real = '{"style": "glass", "font_scale": 1.25}'

    def read(p):
        with open(p, encoding="utf-8") as f:
            return f.read()

    def write(p, s):
        with open(p, "w", encoding="utf-8") as f:
            f.write(s)

    try:
        # ① 备份路径要带脚本名（旧版共用同一路径 → 并行互相删备份）
        assert os.path.basename(cs.bak_path()).startswith("config.json.prevbak."), cs.bak_path()
        assert cs.bak_path() != cs.LEGACY_BAK

        # ② 有配置：临时桩必须真生效，还原必须一字不差，收尾不留痕
        write(cs.CFG, real)
        cs.begin(hotkeys=False, idle_saver=False)
        assert json.loads(read(cs.CFG)) == {"hotkeys": False, "idle_saver": False}
        assert read(cs.bak_path()) == real, "备份里必须是原配置"
        assert os.path.exists(cs.LOCK), "沙箱应当持锁"
        cs.restore()
        assert read(cs.CFG) == real, "还原后必须与原配置一字不差"
        assert not os.path.exists(cs.bak_path()), "备份文件应当被清掉"
        assert not os.path.exists(cs.LOCK), "锁应当被放掉"

        # ③ 备份被别处删掉时，还原不许抛（旧版就是在这里崩的）
        write(cs.CFG, real)
        cs.begin(hotkeys=False)
        os.remove(cs.bak_path())
        cs.restore()                                  # 不抛即通过

        # ④ 原本没有配置 → 退出后不能留下临时桩冒充用户配置
        os.remove(cs.CFG)
        cs.begin(idle_saver=False)
        assert os.path.exists(cs.CFG), "沙箱生效期间应当有临时配置"
        cs.restore()
        assert not os.path.exists(cs.CFG), "原本无配置时不该留下临时桩"

        # ⑤ 残留锁：持有进程已死 → 必须**立刻**抢占
        #    （只看 mtime 会让上次崩溃留下的锁把下一次运行白等整个 timeout）
        write(cs.LOCK, "999999")                   # 这个 pid 必然不存在
        t0 = time.time()
        assert cs._acquire_lock(timeout=5.0) is True, "持有者已消失的锁应当被抢占"
        assert time.time() - t0 < 1.0, "pid 已死就该立刻抢，不该等 mtime 变陈旧"
        cs._release_lock()

        # ⑥ pid 读不出来时退回 mtime 判定：够旧的锁也该抢
        write(cs.LOCK, "not-a-pid")
        os.utime(cs.LOCK, (time.time() - cs.LOCK_STALE - 5,) * 2)
        assert cs._acquire_lock(timeout=0.1) is True, "读不出 pid 时应当按 mtime 抢陈旧锁"
        cs._release_lock()

        # ⑦ 真有人在跑（pid 活着）：应当等满超时，而不是硬闯
        write(cs.LOCK, str(os.getpid()))           # 自己 = 活着的持有者
        t0 = time.time()
        got = cs._acquire_lock(timeout=0.6)
        waited = time.time() - t0
        assert got is False, "活锁不该被抢"
        assert waited >= 0.5, "应当等满超时（实等 %.2fs）" % waited
        cs._release_lock()

        # ⑧ 上下文管理器同样要还原
        write(cs.CFG, real)
        with cs.sandbox(glow=False):
            assert json.loads(read(cs.CFG)) == {"glow": False}
        assert read(cs.CFG) == real
    finally:
        cs.CFG, cs.LOCK, cs.LEGACY_BAK = saved_paths
        cs._state.clear()
        cs._state.update(saved_state)      # 交还真实沙箱的状态，别让收尾还原变空操作
        shutil.rmtree(tmp, ignore_errors=True)


check("cfg sandbox", cfg_sandbox)


# ---------------------------------------------------------------------------
print("[32] 悬停控制条避让 / 首句入场落点 / 换歌清残句")
# ---------------------------------------------------------------------------


def _jump_size_anim():
    """把尺寸动画直接跳到终点：离屏环境没有事件循环，不跳的话窗口尺寸不动"""
    ov._size_anim.setCurrentTime(ov._size_anim.duration())


def hover_avoid():
    """悬停控制条必须完全落到内容区之外。

    旧版胶囊锚死窗口右下角、悬停不让布局让位，实测 5 种样式里 3 种会把
    下一句歌词盖住，进度条和时间文本也必然被压。现在悬停时窗口底部为
    胶囊预留一行，绘制与测试都从 `_content_rect()` 取同一几何。
    """
    fake_song()
    ov._ctrl_t = 0.0
    for style in L.STYLE_NAMES:
        ov.set_style_mode(style)
        ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
        ov._hovered = False
        ov._relayout()
        _jump_size_anim()
        h0 = ov.height()
        m = ov._margin()

        ov._hovered = True                       # 进入悬停：窗口为胶囊让位
        ov._relayout()
        _jump_size_anim()
        h1 = ov.height()
        assert h1 >= h0 + ov.CTRL_H, (style, h0, h1)
        card, cr = ov._content_rect(), ov._ctrl_rect()
        assert not card.intersects(cr), (style, card, cr)
        assert cr.bottom() <= ov.height() - m + 0.5, (style, cr.bottom(), ov.height() - m)

        ov._on_ctrl_anim(0.0)                    # 离开悬停：胶囊淡出后收回预留行
        _jump_size_anim()
        assert abs(ov.height() - h0) <= 2, (style, h0, ov.height())

    # 探针自检：完整复现旧版行为 —— 预留行归零 + 胶囊锚回窗口底边（现在锚的
    # 是内容区下缘，光归零预留行已经压不到内容了），上面的断言必须真的会失败
    ov.set_style_mode("glass")
    ov._relayout()
    _jump_size_anim()
    ov._hovered = True
    ov._ctrl_reserve = lambda: 0
    orig_rect = L.LyricOverlay._ctrl_rect
    L.LyricOverlay._ctrl_rect = lambda self: QRectF(
        self.width() - self._margin() - self.CTRL_N * self.CTRL_CELL - 8,
        self.height() - self._margin() - self.CTRL_H,
        self.CTRL_N * self.CTRL_CELL + 8, self.CTRL_H)
    try:
        _jump_size_anim()
        assert ov._content_rect().intersects(ov._ctrl_rect()), "变异未被触发：避让断言是恒真的"
    finally:
        del ov._ctrl_reserve
        L.LyricOverlay._ctrl_rect = orig_rect
    ov._hovered = False
check("hover 控制条不压内容", hover_avoid)


def ctrl_capsule_dark():
    """控制条胶囊必须是深色玻璃，不能被上游漏下的白色画刷整块填白。

    根因：_draw_progress 画完白色滑块后没有复位画刷，而 _paint_controls 用
    drawPath(bg) 画 1px 边框 —— drawPath 会顺带用「当前画刷」填充路径，于是
    整条胶囊被涂成 #ffffff，在浅色壁纸上糊成一坨（就是「菜单显示异常、可读性
    差」那张截图）。修复：进度条用 save/restore 兜底 + _stroke() 统一在描边
    前强制 NoBrush。
    """

    def sample(style):
        fake_song()
        ov.set_style_mode(style)
        ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
        ov.status = "PLAYING"
        ov._hovered = True
        ov._ctrl_t = 1.0
        ov._relayout()
        _jump_size_anim()
        img = ov.grab().toImage()
        sx = img.width() / max(1, ov.width())
        r = ov._ctrl_rect()
        # 取胶囊内靠上的一条水平带（避开图标），命中顶部内高光也不影响"深色"判断
        y = int((r.top() + r.height() * 0.30) * sx)
        xs = [int(x * sx) for x in range(int(r.left() + r.height() / 2),
                                         max(int(r.left() + r.height() / 2) + 1,
                                             int(r.right() - r.height() / 2)), 3)]
        px = [img.pixelColor(x, y) for x in xs if 0 <= x < img.width()]
        px = [c for c in px if c.alpha() > 0]
        assert px, (style, "采样点全透明：胶囊根本没画出来")
        px.sort(key=lambda c: c.red() + c.green() + c.blue())
        return px[len(px) // 2]                                  # 中位色，抗单点噪声

    for style in L.STYLE_NAMES:
        c = sample(style)
        assert c.alpha() > 150, (style, "胶囊透明度异常", c.alpha())
        assert max(c.red(), c.green(), c.blue()) < 90, \
            (style, "控制条被填成亮色块（画刷泄漏）", c.red(), c.green(), c.blue())

    # 变异自检：把 _stroke 换回"不复位画刷 + 当前画刷是白"的旧行为，上面的
    # 深色断言必须真的翻车 —— 否则恒真断言和通过断言长得一模一样
    orig = L.LyricOverlay._stroke
    L.LyricOverlay._stroke = lambda self, p, path, pen: (
        p.setBrush(QColor(255, 255, 255)), p.setPen(pen), p.drawPath(path))
    try:
        c = sample("glass")
        still_dark = c.alpha() > 150 and max(c.red(), c.green(), c.blue()) < 90
        assert not still_dark, "变异未被触发：胶囊颜色断言是恒真的"
    finally:
        L.LyricOverlay._stroke = orig
    ov._hovered = False
check("控制条是深色玻璃（非白块）", ctrl_capsule_dark)


def hover_no_squish():
    """加高动画期间内容区不许被压扁（卡片主题上是一次可见塌陷）。

    `_content_rect` 原本是「当前窗口高 − 边距 − 预留行」：悬停刚触发时窗口还是
    旧高度、预留行却已经生效 → 内容区先被切掉一整行（48px），再随 300ms 加高
    动画弹回来。iOS 这种整块实心卡片的主题上就是一次明显塌陷，胶囊跟着卡片
    下缘上下滑、还被窗口边切掉一截。现在内容尺寸只由 _relayout 决定。
    """
    fake_song()
    ov.set_style_mode("ios")
    ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
    ov.status = "PLAYING"
    ov._hovered = False
    ov._relayout()
    _jump_size_anim()
    card0 = QRectF(ov._content_rect())
    assert card0.height() > 0, "内容区高度不应为 0（_layout_size 没生效？）"

    ov._hovered = True
    ov._relayout()
    dur = ov._size_anim.duration()
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        ov._size_anim.setCurrentTime(dur * frac)
        card = ov._content_rect()
        assert abs(card.height() - card0.height()) < 0.5, \
            (frac, card0.height(), card.height(), "加高动画期间内容区不许塌陷")
        assert abs(card.width() - card0.width()) < 0.5, (frac, card0.width(), card.width())
    _jump_size_anim()

    # 变异自检：换回「按当前窗口高反推」的旧公式，上面必须翻车
    orig = L.LyricOverlay._content_rect

    def old_rect(self):
        mm = self._margin()
        return QRectF(mm, mm, self.width() - 2 * mm,
                      self.height() - 2 * mm - self._ctrl_reserve())

    L.LyricOverlay._content_rect = old_rect
    try:
        ov._hovered = False
        ov._relayout()
        _jump_size_anim()
        base = QRectF(ov._content_rect())
        ov._hovered = True
        ov._relayout()
        ov._size_anim.setCurrentTime(0)
        squashed = abs(ov._content_rect().height() - base.height()) > 0.5
        assert squashed, "变异未被触发：塌陷断言是恒真的"
    finally:
        L.LyricOverlay._content_rect = orig
    ov._hovered = False
    ov._relayout()
    _jump_size_anim()
check("加高动画不压内容（无塌陷）", hover_no_squish)


def hover_no_flap():
    """悬停加高/收回全程，胶囊与内容在屏幕上的位置必须钉死不动。

    旧版胶囊锚窗口底边：悬停加高的 300ms 动画里胶囊跟着底边下滑 48px，鼠标
    指着的点变成透明像素 —— 本窗口是逐像素命中的分层窗口（alpha=0 处直接
    穿透），OS 立刻判定「离开」→ 收回预留行 → 光标又指回胶囊 → 再进入 …
    无限循环，表现就是用户报的「悬停时乱跳」。另：鼠标从内容移向胶囊要跨过
    中间的透明间隙，OS 也会发 leave —— 淡出改由帧循环轮询全局光标触发。
    """
    fake_song()
    ov.set_style_mode("glass")
    ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
    ov.status = "PLAYING"
    ov._hovered = False
    ov._ctrl_t = 1.0                       # 不参与几何，只是让两次取样可比
    ov._relayout()
    _jump_size_anim()
    cr0 = QRectF(ov._ctrl_rect())
    card0 = QRectF(ov._content_rect())
    pos0 = QPoint(ov.pos())

    ov._hovered = True                     # 进入悬停：窗口加高，胶囊不许挪
    ov._relayout()
    _jump_size_anim()
    assert ov.pos() == pos0, (ov.pos(), pos0, "free 摆放不该因悬停挪窗")
    card1 = ov._content_rect()
    assert card1.topLeft() == card0.topLeft(), (card0, card1, "内容区不该被悬停挪动")
    cr1 = ov._ctrl_rect()
    assert cr1.topLeft() == cr0.topLeft(), (cr0.topLeft(), cr1.topLeft(),
                                            "胶囊不该跟着窗口底边滑走")

    # 淡出走轮询：光标还在窗口矩形内（哪怕 OS 因透明像素已报 leave）不收条，
    # 真出了矩形才收。光标打桩在 _cursor_global，不碰真实鼠标。
    real_cursor = ov._cursor_global
    inside = ov.mapToGlobal(QPoint(int(ov.width() / 2), int(ov.height() / 2)))
    outside = inside + QPoint(100000, 100000)
    try:
        ov._hovered = True
        ov._animate_ctrl(1.0)
        ov._cursor_global = lambda: inside
        ov._on_frame()
        assert float(ov._ctrl_anim.endValue()) == 1.0, "光标还在悬浮层内不许触发淡出"

        ov._cursor_global = lambda: outside
        ov._on_frame()
        assert (ov._ctrl_anim.state() == QVariantAnimation.Running
                and float(ov._ctrl_anim.endValue()) == 0.0), "光标真出了窗口矩形才收条"
        ov._on_ctrl_anim(0.0)              # 淡出播完：收回预留行
        assert not ov._hovered, "淡出结束后必须收回预留行"
    finally:
        ov._cursor_global = real_cursor
    ov._hovered = False
    ov._ctrl_t = 0.0

    # 变异自检：把胶囊换回「锚窗口底边」的旧行为，上面的“不挪动”断言必须翻车
    orig_rect = L.LyricOverlay._ctrl_rect

    def old_rect(self):
        w = self.CTRL_N * self.CTRL_CELL + 8
        m = self._margin()
        return QRectF(self.width() - m - w, self.height() - m - self.CTRL_H, w,
                      self.CTRL_H)

    L.LyricOverlay._ctrl_rect = old_rect
    try:
        ov._hovered = False
        ov._relayout()
        _jump_size_anim()
        a = ov._ctrl_rect().topLeft()
        ov._hovered = True
        ov._relayout()
        _jump_size_anim()
        b = ov._ctrl_rect().topLeft()
        assert a != b, "变异未被触发：胶囊锚点断言是恒真的"
    finally:
        L.LyricOverlay._ctrl_rect = orig_rect
    ov._hovered = False
    ov._relayout()
    _jump_size_anim()
check("悬停加高不挪胶囊 / 光标轮询防抖", hover_no_flap)


def first_line_slot():
    """前奏期第一句直接占当前行（未唱态：逐字进度按 pos 实时算，此刻全暗、
    无填色），下一行挂第二句；唱到时逐字自然点亮，不再有"当前行显示歌名/
    纯音乐占位、第一句缩在下一行小字里"的状态 —— 用户会当成"第一行歌词不
    显示"（纯音乐占位更是误导，明明有歌词）。"""
    fake_song()
    ov.lines = [[5.0, "第一句歌词"], [8.0, "第二句歌词"]]
    ov.words = {}
    ov.trans = []
    ov._trans_map = {}
    ov._reset_line_state()
    ov._line_t = 1.0
    ov.anim_style = "slide"
    ov.status = "PLAYING"

    karaoke_texts, plain_texts = [], []
    ov._draw_karaoke = lambda p, text, *a, **k: karaoke_texts.append(text)
    ov._draw_plain = lambda p, text, *a, **k: plain_texts.append(text)
    try:
        # 前奏（pos=0）：第一句已在当前行，下一行是第二句
        ov.anchor_pos = 0.0
        ov.anchor_ts = time.monotonic()
        ov._on_frame()
        assert (ov.cur_idx, ov._current_text, ov._next_text) == (0, "第一句歌词", "第二句歌词"), \
            (ov.cur_idx, ov._current_text, ov._next_text)
        karaoke_texts.clear()
        plain_texts.clear()
        _render()
        assert karaoke_texts == ["第一句歌词"], \
            (karaoke_texts, plain_texts, "前奏期当前行必须是第一句（未唱态走卡拉OK渲染）")
        assert not any("纯音乐" in t or "第一句歌词" in t for t in plain_texts), \
            (plain_texts, "第一句不许再缩在下一行小字里，占位文案也不许出现")

        # 唱到第一句：状态不切换（行已就位，不重播入场动画），卡拉OK照常走
        ov.anchor_pos = 6.0
        ov.anchor_ts = time.monotonic()
        ov._line_anim.stop()               # 把前奏开始时播的入场动画停下来
        ov._line_t = 1.0
        ov._on_frame()
        assert ov._current_text == "第一句歌词", ov._current_text
        assert ov._line_anim.state() != QVariantAnimation.Running, \
            "第一句已在位，唱到时不该重播入场动画"
        n = len(karaoke_texts)
        _render()
        assert len(karaoke_texts) > n, "有歌词的当前行必须走卡拉OK"

        # 第一句不能被跳过：9s 时当前行应是第二句（文本变了 → 入场动画照播）
        ov.anchor_pos = 9.0
        ov.anchor_ts = time.monotonic()
        ov._on_frame()
        assert ov._current_text == "第二句歌词", ov._current_text
        assert ov._line_anim.state() == QVariantAnimation.Running, "切行必须带入场动画"

        # 变异自检：把前奏回退换回旧行为（当前行空、第一句压在下一行），上面的
        # "当前行=第一句"断言必须翻车
        orig = L.LyricOverlay._prelude_texts
        L.LyricOverlay._prelude_texts = lambda self: ("", self.lines[0][1])
        try:
            ov._reset_line_state()
            ov.anchor_pos = 0.0
            ov.anchor_ts = time.monotonic()
            ov._on_frame()
            still = ov._current_text == "第一句歌词"
            assert not still, "变异未被触发：前奏断言是恒真的"
        finally:
            L.LyricOverlay._prelude_texts = orig
    finally:
        del ov._draw_karaoke
        del ov._draw_plain
    ov._reset_line_state()
check("首句入场落点", first_line_slot)


def no_lyric_hint_scope():
    """「♫ 纯音乐或暂无歌词」只许在真没歌词时出现。

    有歌词但还没唱到时当前行是第一句（未唱态），不该看到占位文案 ——
    那会让人以为歌词丢了（用户反馈截图里前奏期显示"纯音乐或暂无歌词"
    就是这个坑）。"""
    fake_song()
    ov.set_style_mode("glass")
    ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
    ov.status = "PLAYING"

    plain_texts = []
    ov._draw_plain = lambda p, text, *a, **k: plain_texts.append(text)
    try:
        # 真没歌词：显示占位
        ov.lines = []
        ov._reset_line_state()
        ov._relayout()
        plain_texts.clear()
        _render()
        assert any("纯音乐" in t for t in plain_texts), \
            (plain_texts, "真没歌词时必须有纯音乐占位")

        # 有歌词、前奏期：不许出现占位
        ov.lines = [[30.0, "前奏很长的一句"], [40.0, "第二句"]]
        ov._reset_line_state()
        ov.anchor_pos = 10.0
        ov.anchor_ts = time.monotonic()
        ov._on_frame()
        ov._relayout()
        _jump_size_anim()
        plain_texts.clear()
        _render()
        assert not any("纯音乐" in t for t in plain_texts), \
            (plain_texts, "有歌词但还没唱到时不许显示纯音乐占位")
        assert any("前奏很长的一句" in t for t in plain_texts) or ov._current_text == "前奏很长的一句", \
            (plain_texts, ov._current_text, "前奏期第一句必须可见")
    finally:
        del ov._draw_plain
    ov._reset_line_state()
check("纯音乐占位只在真没歌词时出现", no_lyric_hint_scope)


def song_switch_clears():
    """换歌 / 重取歌词后、新内容到达前，上一首的残句必须清掉。

    旧版只归零 cur_idx 不清 _current_text/_next_text，新歌歌词没到时
    （lines == []，主循环整段跳过），上一首最后一句会画在新歌歌名位置上。
    """
    fake_song()
    assert ov._current_text
    ov._apply_media(None)                    # 播放器停播：整行状态一起清
    assert (ov.cur_idx, ov._current_text, ov._next_text) == (-1, "", ""), \
        (ov.cur_idx, ov._current_text, ov._next_text)

    fake_song()
    ov._req_id += 1
    ov._on_fetched((ov._req_id, [], {}, None, []))   # 新歌词到达（空 = 纯音乐）
    assert (ov.cur_idx, ov._current_text, ov._next_text) == (-1, "", ""), \
        (ov.cur_idx, ov._current_text, ov._next_text)
check("换歌清残句", song_switch_clears)


def clamp_to_screen():
    """窗口必须整个落在所在屏幕的工作区里（自由摆放贴边 / 悬停加高都一样）。

    用户实测两个症状同根因：自由摆放的窗口停在屏幕边缘外 → 卡片被屏幕裁掉
    一块；悬停为控制条加高的 48px 朝屏幕外侧长 → 控制条整行落到屏幕外"出
    不来"。现在任何尺寸变化 / 拖拽 / 显示 / 恢复配置都会把窗口夹回工作区。
    """
    fake_song()
    ov.set_style_mode("glass")
    ov.glow = ov.show_trans = ov.show_time = ov.show_cover = True
    ov.status = "PLAYING"
    ov._hovered = False
    ov.pos_preset = L.POS_FREE
    ov._relayout()
    _jump_size_anim()
    avail = ov.screen().availableGeometry()

    # ① 单元：夹屏函数本身要把屏外窗口拉回工作区
    ov.move(avail.right() + 120, avail.bottom() + 80)
    ov._clamp_into_screen()
    g = ov.frameGeometry()
    assert (g.left() >= avail.left() and g.top() >= avail.top()
            and g.right() <= avail.right() and g.bottom() <= avail.bottom()), (g, avail)

    # ② 集成：贴着工作区底缘时悬停加高，控制条不许落到屏幕外
    ov.move(avail.left() + 60, avail.bottom() - ov.height() + 1)
    ov._hovered = True
    ov._relayout()
    _jump_size_anim()
    g = ov.frameGeometry()
    assert g.bottom() <= avail.bottom(), (g.bottom(), avail.bottom(), "悬停加高后窗口底越过工作区")
    cap_bottom = g.top() + int(ov._ctrl_rect().bottom())
    assert cap_bottom <= avail.bottom(), (cap_bottom, avail.bottom(), "控制条落到屏幕外")

    # ③ 离开悬停、收回预留行之后窗口仍要完整在工作区内
    ov._on_ctrl_anim(0.0)
    _jump_size_anim()
    g = ov.frameGeometry()
    assert g.bottom() <= avail.bottom() and g.top() >= avail.top(), (g, avail)

    # 变异自检：禁用夹屏，②的悬停加高必须把窗口顶出工作区
    orig = L.LyricOverlay._clamp_into_screen
    L.LyricOverlay._clamp_into_screen = lambda self: None
    try:
        ov.move(avail.left() + 60, avail.bottom() - ov.height() + 1)
        ov._hovered = True
        ov._relayout()
        _jump_size_anim()
        assert ov.frameGeometry().bottom() > avail.bottom(), \
            "变异未被触发：夹屏断言是恒真的"
    finally:
        L.LyricOverlay._clamp_into_screen = orig
        ov._hovered = False
        ov._relayout()
        _jump_size_anim()
check("窗口夹回屏幕工作区", clamp_to_screen)


print("[33] 悬停淡入启动脉冲不复位悬停态（控制条只展开一半）")
def ctrl_fadein_pulse():
    """QVariantAnimation 在 setEndValue()（state 还是 Stopped）就会同步发一次
    valueChanged(起始值)。从 ctrl_t=0 淡入时这个值是 0.0，旧 _on_ctrl_anim 把
    它误判成「淡出结束」→ 复位 _hovered → _relayout 收回 48px 预留行 → 窗口
    塌回矮高度、胶囊却淡到全不透明，36px 高的胶囊被裁得只剩几像素 —— 用户看到
    的「控制条只展开一半」，且随歌词长度变化（换行触发 _relayout 重启加高动画）
    时机一变就随机复现。修复：_animate_ctrl 装弹期间抑制该脉冲。"""
    fake_song()
    ov.set_style_mode("glass")
    ov.status = "PLAYING"

    def jump_ctrl():
        ov._ctrl_anim.setCurrentTime(ov._ctrl_anim.duration())

    ov._hovered = False
    ov._ctrl_t = 0.0
    ov._relayout()
    _jump_size_anim()
    base_h = ov.height()

    # 走 enterEvent 的真实路径：enter → 加高动画 Running → 150ms 后淡入
    ov._hovered = True
    ov._relayout()
    assert ov._size_anim.state() == QPropertyAnimation.Running
    _jump_size_anim()
    hover_h = ov.height()
    assert hover_h - base_h == ov._ctrl_reserve(), (base_h, hover_h)
    ov._show_ctrl_if_hover()               # singleShot(150) 到期后的真实调用
    jump_ctrl()                            # 淡入播完（真实 tick 也会发 1.0）
    assert ov._hovered is True, "淡入的启动脉冲不许复位悬停态"
    assert abs(float(ov._ctrl_t) - 1.0) < 1e-6, ov._ctrl_t
    assert ov.height() == hover_h, (ov.height(), hover_h, "淡入期间窗口不许塌回")
    cr = QRectF(ov._ctrl_rect())
    assert cr.bottom() <= ov.height() and cr.top() >= 0, \
        (cr, ov.height(), "胶囊必须完整落在窗口内")

    # 正常淡出仍然要收回预留行（抑制脉冲不能把真淡出也拦了）
    ov._animate_ctrl(0.0)
    jump_ctrl()
    assert not ov._hovered, "淡出结束后必须收回预留行"
    ov._relayout()
    _jump_size_anim()
    assert ov.height() == base_h, (ov.height(), base_h)

    # 变异自检：换回「装弹不设抑制标志」的旧 _animate_ctrl，上面的悬停态
    # 断言必须翻车（证明测试真的逮得住这个时序 bug）
    orig_anim = L.LyricOverlay._animate_ctrl

    def old_animate(self, target):
        self._ctrl_anim.stop()
        self._ctrl_anim.setStartValue(self._ctrl_t)
        self._ctrl_anim.setEndValue(target)
        self._ctrl_anim.start()

    L.LyricOverlay._animate_ctrl = old_animate
    try:
        ov._hovered = False
        ov._ctrl_t = 0.0
        ov._relayout()
        _jump_size_anim()
        ov._hovered = True
        ov._relayout()
        _jump_size_anim()
        ov._show_ctrl_if_hover()           # 旧代码：启动脉冲 0.0 → 复位悬停
        assert not ov._hovered, "变异未被触发：启动脉冲断言是恒真的"
    finally:
        L.LyricOverlay._animate_ctrl = orig_anim
        ov._hovered = False
        ov._ctrl_t = 0.0
        ov._relayout()
        _jump_size_anim()
check("悬停淡入启动脉冲不复位悬停态", ctrl_fadein_pulse)


print("[34] 窄窗悬停：胶囊两端都不得被窗口裁掉")
def ctrl_narrow_window():
    """胶囊宽 212 固定不随字号缩放，而原生浮字「短歌词 + font_scale 0.7」的
    窗口最小宽只有约 202px（ios 约 207px）—— _ctrl_rect 右锚定
    `width - m - 212` 会算出负的左边，胶囊左端（上一首按钮整格）被窗口裁掉。
    修复：悬停时窗口宽度保底 `_ctrl_min_window_w()`（300ms 动画顺带加宽），
    `_ctrl_rect` 再把矩形夹回窗口内兜底；收回悬停后窗口缩回原尺寸。"""
    fake_song()
    ov.set_style_mode("native")
    ov.font_scale = 0.7
    ov.lines = [[0.0, "一百遍"], [3.0, "又一百遍"]]
    ov.words = {}
    ov.trans = []
    ov._trans_map = {}
    ov.show_trans = ov.show_time = ov.show_cover = False
    ov._reset_line_state()
    ov._line_t = 1.0
    ov._current_text = "一百遍"
    ov._next_text = "又一百遍"
    ov.status = "PLAYING"
    ov._hovered = False
    ov._ctrl_t = 0.0
    ov._relayout()
    _jump_size_anim()
    base_w = ov.width()
    assert base_w < ov._ctrl_min_window_w(), \
        (base_w, "前提：原生短句窗口确实装不下胶囊")

    ov._hovered = True
    ov._relayout()
    _jump_size_anim()
    w = ov.width()
    assert w >= ov._ctrl_min_window_w(), (w, "悬停时窗口必须装得下整条胶囊")
    r = QRectF(ov._ctrl_rect())
    assert r.left() >= 0 and r.right() <= w, (r, w, "胶囊两端都不许出窗")

    # 收回悬停：窗口缩回窄尺寸。202px 的窗口物理上装不下 212px 的胶囊，
    # 但此刻胶囊透明度为 0 且不参与命中（_ctrl_t<0.5 直接 -1），露头无害；
    # 这里只断言夹回兜底把左端拉回了窗内
    ov._hovered = False
    ov._relayout()
    _jump_size_anim()
    assert ov.width() == base_w, (ov.width(), base_w)
    r2 = QRectF(ov._ctrl_rect())
    assert r2.left() >= 0, (r2, "夹回兜底：左端不得为负")

    # 变异自检：去掉宽度保底，右侧出窗断言必须翻车
    orig = L.LyricOverlay._ctrl_min_window_w
    L.LyricOverlay._ctrl_min_window_w = lambda self: 0
    try:
        ov._hovered = True
        ov._relayout()
        _jump_size_anim()
        r3 = QRectF(ov._ctrl_rect())
        assert r3.right() > ov.width() or r3.left() < 0, \
            "变异未被触发：胶囊出窗断言是恒真的"
    finally:
        L.LyricOverlay._ctrl_min_window_w = orig
        ov._hovered = False
        ov._relayout()
        _jump_size_anim()
check("窄窗悬停胶囊不出窗", ctrl_narrow_window)


# ---- 收尾：注销热键、还原配置 ----
ov.hotkeys.unregister()
ov._save_position()
_cfg_sandbox.restore()
print("[cfg] 测试配置已还原")

print("\n==== 结果: %s ===="
      % ("全部通过" if not fails else "失败 %d 项: %s" % (len(fails), fails)))
sys.exit(1 if fails else 0)
