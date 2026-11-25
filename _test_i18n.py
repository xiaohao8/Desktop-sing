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
L._source_mark("qq", False); L._source_mark("qq", False)
ck("源健康计数", L._SOURCE_HEALTH["qq"]["fail"] == 2)
ck("score 罚分生效", L.score_lyrics([[0.0, "a"], [999999.0, "b"]], {}, [], 200.0) < 0)
print("----", "FAIL: %d" % len(fails) if fails else "全部通过")
sys.exit(1 if fails else 0)
