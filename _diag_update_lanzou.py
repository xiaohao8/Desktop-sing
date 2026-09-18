# -*- coding: utf-8 -*-
"""内置蓝奏云更新源自测：验证多源探测、镜像挂载、版本比较与降级回落。"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lyrics_overlay as L  # noqa: E402

app = QApplication.instance() or QApplication([])


class Stub(QObject):
    update_checked = Signal(object)

    def __init__(self):
        super().__init__()
        self.got = []
        self.update_checked.connect(lambda p: self.got.append(p))

    run = L.LyricOverlay._check_update_worker


def fake_http_factory(mapping):
    def _get(url, headers=None, timeout=6.0):
        for key, payload in mapping.items():
            if key in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise RuntimeError("no such url: %s" % url)
    return _get


def gh_release(ver):
    return json.dumps({
        "tag_name": "v" + ver,
        "name": "Desktop-sing v" + ver,
        "body": "更新说明测试",
        "assets": [
            {"name": "Desktop-sing-v%s-portable.zip" % ver,
             "browser_download_url": "https://example.com/p.zip"},
            {"name": "Desktop-sing-v%s-setup.exe" % ver,
             "browser_download_url": "https://example.com/s.exe"},
        ],
    }).encode("utf-8")


results = []


def case(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  | " + extra) if extra else ""))


print("== 内置常量 ==")
case("默认更新源指向 GitHub API", L.DEFAULT_UPDATE_URL ==
     "https://api.github.com/repos/xiaohao8/Desktop-sing/releases/latest", L.DEFAULT_UPDATE_URL)
case("蓝奏云镜像表收录 1.0.0", bool(L.lanzou_mirror("1.0.0").get("setup")))
case("未收录版本返回空", L.lanzou_mirror("9.9.9") == {})
case("版本号带 v 前缀也能查", bool(L.lanzou_mirror("v1.0.0").get("portable")))

print("\n== 主源命中新版本（GitHub 返回 1.1.0，镜像表无该版本）==")
st = Stub()
L.http_get = fake_http_factory({"api.github.com": gh_release("1.1.0"),
                                "jsdelivr": RuntimeError("boom")})
st.run(L.DEFAULT_UPDATE_URL, True)
p = st.got[-1]
case("判定为有更新", p.get("has_update") is True)
case("取到 exe 而非 zip", (p.get("url") or "").endswith("s.exe"), p.get("url"))
case("未收录版本不带蓝奏云键", not p.get("lanzou_setup"))

print("\n== 主源挂了 → 走国内清单镜像（update.json 自带蓝奏云）==")
manifest = json.dumps({
    "version": "1.0.1",
    "lanzou_setup": "https://wwbgk.lanzouu.com/NEWSETUP",
    "lanzou_portable": "https://wwbgk.lanzouu.com/NEWPORTABLE",
    "notes": "新版本说明",
}).encode("utf-8")
st = Stub()
L.http_get = fake_http_factory({"api.github.com": RuntimeError("GitHub 不通"),
                                "jsdelivr": manifest})
st.run(L.DEFAULT_UPDATE_URL, True)
p = st.got[-1]
case("镜像源救回更新提示", p.get("has_update") is True)
case("携带蓝奏云安装版", p.get("lanzou_setup", "").endswith("NEWSETUP"), p.get("lanzou_setup"))
case("携带蓝奏云免安装版", p.get("lanzou_portable", "").endswith("NEWPORTABLE"))
case("无资源直链时回落到 Releases 页", "github.com/xiaohao8/Desktop-sing/releases" in (p.get("url") or ""))

print("\n== 内置镜像表兜底（GitHub 报 1.0.0 的下一版，表里已有链接）==")
L.LANZOU_MIRRORS["2.0.0"] = {"setup": "https://wwbgk.lanzouu.com/S2",
                             "portable": "https://wwbgk.lanzouu.com/P2"}
st = Stub()
L.http_get = fake_http_factory({"api.github.com": gh_release("2.0.0"),
                                "jsdelivr": RuntimeError("404")})
st.run(L.DEFAULT_UPDATE_URL, True)
p = st.got[-1]
case("内置镜像补进结果", p.get("lanzou_setup") == "https://wwbgk.lanzouu.com/S2", p.get("lanzou_setup"))
del L.LANZOU_MIRRORS["2.0.0"]

print("\n== 已是最新 / 全部失败 ==")
st = Stub()
L.http_get = fake_http_factory({"api.github.com": gh_release("1.0.0"),
                                "jsdelivr": RuntimeError("404")})
st.run(L.DEFAULT_UPDATE_URL, True)
case("同版本不提示", st.got[-1].get("has_update") is False and
     "已是最新" in (st.got[-1].get("msg") or ""), st.got[-1].get("msg"))

st = Stub()
L.http_get = fake_http_factory({"api.github.com": RuntimeError("timeout"),
                                "jsdelivr": RuntimeError("timeout")})
st.run(L.DEFAULT_UPDATE_URL, True)
case("全失败只报一次失败", st.got[-1].get("has_update") is False and
     "失败" in (st.got[-1].get("msg") or ""), st.got[-1].get("msg"))
case("不会重复弹多条", len(st.got) == 1, "收到 %d 条" % len(st.got))

print("\n== 本地 update.json 可被解析 ==")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "update.json"), "rb") as f:
    info = L.parse_update_payload(f.read(), "local")
case("版本号解析正确", info and info["version"] == "1.0.0")
case("透传蓝奏云键", info and bool(info.get("lanzou_setup")) and bool(info.get("lanzou_portable")))

bad = [r for r in results if not r[1]]
print("\n合计 %d 项，失败 %d 项" % (len(results), len(bad)))
sys.exit(1 if bad else 0)
