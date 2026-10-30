# -*- coding: utf-8 -*-
"""v1.0.2 发布后实测更新链路：各版本存量用户会不会收到提示、按钮指向哪里。"""
import io
import json
import os
import sys
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cfg_sandbox                                             # noqa: E402
_cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)
import lyrics_overlay as L                                      # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("APP_VERSION =", L.APP_VERSION)
print("主源 =", L.DEFAULT_UPDATE_URL)
print("兜底 =", L.UPDATE_FALLBACK_SOURCES)
print("内置蓝奏云表 =", L.LANZOU_MIRRORS)

raw = urllib.request.urlopen(L.DEFAULT_UPDATE_URL, timeout=25).read()
info = L.parse_update_payload(raw, L.DEFAULT_UPDATE_URL)
print("\n主源返回: version=%s url=%s" % (info["version"], info["url"]))
print("主源蓝奏云镜像 =", L.lanzou_mirror(info["version"]) or "无（按钮回落 GitHub）")

local = json.load(io.open("update.json", encoding="utf-8"))
mir_info = L.parse_update_payload(json.dumps(local).encode("utf-8"), "update.json")
print("\n仓库清单镜像: version=%s url=%s" % (mir_info["version"], mir_info["url"]))
lz = {k: v for k, v in mir_info.items() if k.startswith("lanzou")}
print("清单镜像蓝奏云 =", lz or "无（按钮回落 url 字段）")

# UpdateDialog 的主按钮优先级：lanzou_setup -> lanzou_portable -> url
main = (mir_info.get("lanzou_setup") or mir_info.get("lanzou_portable")
        or mir_info.get("url"))
print("更新弹窗主按钮指向 =", main)

print("\n存量用户是否会收到升级提示（主源 v%s）：" % info["version"])
for v in ("1.0.0", "1.0.1", "1.0.1.0", "1.0.2", "1.0.2.0", "2.0.0", "2.0.1", "2.0.1.0"):
    c = L.compare_version(info["version"], v)
    tag = "会提示" if c > 0 else ("已是最新" if c == 0 else "被判成比远端旧")
    print("  本机 %-8s 四段=%-16s -> %s" % (v, L.parse_version(v), tag))
