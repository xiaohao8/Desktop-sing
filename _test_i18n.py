# -*- coding: utf-8 -*-
"""i18n 功能验证：切换语言后托盘菜单 / 占位文案 / 翻译表真实生效。"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)
import _cfg_sandbox
_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)

import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import lyrics_overlay as L
from PySide6.QtWidgets import QApplication

app = QApplication([])
fails = []

def ck(name, cond, extra=""):
    print(("  ok  - " if cond else "  FAIL- ") + name
          + (" | " + str(extra) if extra and not cond else ""))
    if not cond:
        fails.append(name)

# 1) 检测/设置
L.set_ui_lang("en")
ck("en 恒等回退", L._tr("设置面板…") == "Settings…", L._tr("设置面板…"))
L.set_ui_lang("zh-CN")
ck("zh-CN 恒等", L._tr("设置面板…") == "设置面板…")
L.set_ui_lang("ja")
ck("ja 查表", L._tr("退出") == "終了", L._tr("退出"))
L.set_ui_lang("zh-TW")
ck("zh-TW 查表", L._tr("歌词缓存") == "歌詞快取", L._tr("歌词缓存"))
# 缺译回退中文原文
ck("缺译回退", L._tr("不存在的一条文案") == "不存在的一条文案")

# 2) 托盘菜单真实构建：创建后经 cfg 链路切 en（__init__ 会按 cfg 重置为 auto）
ov = L.LyricOverlay(L.MediaWatcher())
ov.set_ui_lang("en")
m = ov.tray.contextMenu()
texts = [a.text() for a in m.actions() if a.text()]
ck("托盘菜单 en", any("Settings" in t for t in texts), str(texts[:3]))
ck("托盘菜单无中文残留", not any(any(ch > '\u2e80' and ch < '\u9fff' or '\u4e00' <= ch <= '\u9fff' for ch in t) for t in texts if t), str(texts[:6]))

# 3) 占位文案（en）
ov.song = {"title": "T", "artist": "A", "cover": None}
ov.lines = []
ov._retry_timer.start(99999)
ov._net_down = True
ck("网络不可用占位 en", ov._idle_current_text() == "♪ Network unavailable, retrying…",
   ov._idle_current_text())
ov._net_down = False
ck("获取失败占位 en", ov._idle_current_text() == "♪ Fetch failed, retrying…",
   ov._idle_current_text())
ov._retry_timer.stop()
ck("纯音乐占位 en", ov._idle_current_text() == "♫ Instrumental or no lyrics",
   ov._idle_current_text())

# 4) 语言切换 retranslate：切回 zh-CN 后托盘菜单变中文
L.set_ui_lang("en")
ov.retranslate_ui()
m2 = ov.tray.contextMenu()
texts2 = [a.text() for a in m2.actions() if a.text()]
ck("rebuild 后仍 en", any("Settings" in t for t in texts2))
ov.set_ui_lang("zh-CN")
m3 = ov.tray.contextMenu()
texts3 = [a.text() for a in m3.actions() if a.text()]
ck("切换后菜单 zh-CN", any("设置面板…" in t for t in texts3), str(texts3[:3]))
ck("配置已存档", ov.cfg.get("ui_lang") == "zh-CN", str(ov.cfg.get("ui_lang")))

empty_stats_key = "还没有足够的听歌记录。播放满 20 秒后才会开始统计。"
for lang in ("zh-TW", "en", "ja"):
    L.set_ui_lang(lang)
    empty_stats_text = L._tr(empty_stats_key)
    ck("报告空态有译文", empty_stats_text != empty_stats_key,
       (lang, empty_stats_text))
    ck("报告空态无简体回退", "记录" not in empty_stats_text
       and "统计" not in empty_stats_text, (lang, empty_stats_text))
L.set_ui_lang("zh-CN")

# 5) 源健康/罗马音/繁简烟雾确认
for lang in ("zh-CN", "zh-TW", "en", "ja"):
    L.set_ui_lang(lang)
    settings = L.SettingsPanel(ov)
    rows = [(btn.text(), btn.fontMetrics().horizontalAdvance(btn.text()),
             btn.minimumWidth())
            for _eid, (btn, _name) in settings._fontrows.items()]
    ck("字体按钮按语言度量取宽",
      all(width >= 92 and width >= advance + 18
          for _text, advance, width in rows),
      (lang, rows))
    settings.close()
L.set_ui_lang("zh-CN")
L._source_mark("qq", False); L._source_mark("qq", False)
ck("源健康计数", L._SOURCE_HEALTH["qq"]["fail"] == 2)
ck("score 罚分生效", L.score_lyrics([[0.0, "a"], [999999.0, "b"]], {}, [], 200.0) < 0)

# 6) lyrics_view.py 里所有 tr()/_tr() 字面量都必须有 en / ja 译文
import ast as _ast


def _tr_call_name(node):
    if isinstance(node, _ast.Name):
        return node.id
    if isinstance(node, _ast.Attribute):
        return node.attr
    return ""


_view_keys = set()
_view_tree = _ast.parse(open(os.path.join(APP_DIR, "lyrics_view.py"),
                             encoding="utf-8").read())
for _node in _ast.walk(_view_tree):
    if isinstance(_node, _ast.Call) and _tr_call_name(_node.func) in ("tr", "_tr"):
        for _arg in _node.args:
            if isinstance(_arg, _ast.Constant) and isinstance(_arg.value, str):
                _view_keys.add(_arg.value)
            elif (isinstance(_arg, _ast.BinOp)
                  and isinstance(_arg.op, _ast.Mod)
                  and isinstance(_arg.left, _ast.Constant)
                  and isinstance(_arg.left.value, str)):
                _view_keys.add(_arg.left.value)
    if isinstance(_node, _ast.Assign):
        for _target in _node.targets:
            if (isinstance(_target, _ast.Name)
                    and _target.id in ("empty_message_key", "empty_description_key")
                    and isinstance(_node.value, _ast.Constant)
                    and isinstance(_node.value.value, str)
                    and _node.value.value.strip()):
                _view_keys.add(_node.value.value)
for _lang in ("en", "ja"):
    L.set_ui_lang(_lang)
    _table = L._I18N_TABLES.get(_lang) or {}
    _missing = sorted(_key for _key in _view_keys
                      if not str(_table.get(_key) or "").strip())
    ck("lyrics_view 文案无缺译 (%s, %d keys)" % (_lang, len(_view_keys)),
       not _missing, _missing[:10])
# 7) 设置页重排：新增键四语言齐全，且设置页文案跟随语言
_refresh_keys = ("应用主题", "歌词外观",
                 "选择应用配色；跟随系统会随 Windows 深浅色切换",
                 "显示内容", "关闭页面淡入和过渡动画")
for _lang in ("zh-TW", "en", "ja"):
    L.set_ui_lang(_lang)
    _table = L._I18N_TABLES.get(_lang) or {}
    _missing = [_k for _k in _refresh_keys if not str(_table.get(_k) or "").strip()]
    ck("设置页重排键无缺译 (%s)" % _lang, not _missing, _missing)
    ck("设置页重排键不回退中文 (%s)" % _lang,
       all(str(_table.get(_k) or "") != _k for _k in _refresh_keys),
       [_k for _k in _refresh_keys if str(_table.get(_k) or "") == _k])

import lyrics_view as _V  # noqa: E402
_page = _V.SettingsPage(ov, L._tr)
for _lang, _title in (("zh-CN", "应用主题"), ("zh-TW", "應用主題"),
                      ("en", "App theme"), ("ja", "アプリテーマ")):
    L.set_ui_lang(_lang)
    _page.retranslate()
    ck("设置页标题跟随语言 (%s)" % _lang,
       _page.appearance.title.text() == _title, _page.appearance.title.text())
    _hint = _page.appearance.hint.text().strip()
    ck("设置页提示跟随语言 (%s)" % _lang,
       bool(_hint) and (_hint == "选择应用配色；跟随系统会随 Windows 深浅色切换")
       == (_lang == "zh-CN"), _hint)
    _motion = _page.appearance.motion_label.text().strip()
    ck("减少动态效果标签跟随语言 (%s)" % _lang,
       bool(_motion) and (_motion == "减少动态效果") == (_lang == "zh-CN"), _motion)
    _names = [btn.name.text().strip() for btn in _page.appearance.swatch_buttons.values()]
    ck("主题卡名称非空 (%s)" % _lang, all(bool(_n) for _n in _names), _names)
    if _lang == "en":
        ck("主题卡名称为英文 (%s)" % _lang,
           all(_n not in ("墨", "青瓷") for _n in _names), _names)
_page.deleteLater()
L.set_ui_lang("zh-CN")

print("----", "FAIL: %d" % len(fails) if fails else "全部通过")
sys.exit(1 if fails else 0)
