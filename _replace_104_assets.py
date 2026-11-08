#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""替换 v1.0.4 Release 的三个资产 + 更新正文（构建含播放状态修复的新包后）。

同 tag 原地替换：发布才数小时、商店未提交、下载量≈0，保持 v1.0.4 版本号
比另立新 tag 干净（update.json / 官网 / 商店材料都不用动）。
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REL = ROOT / "dist" / "release"
REPO = "xiaohao8/Desktop-sing"
VER = "1.0.4"

ASSETS = [
    ("桌面歌词-v1.0.4-安装版.exe", "Desktop-sing-v%s-setup.exe" % VER),
    ("桌面歌词-v1.0.4-免安装极速版.zip", "Desktop-sing-v%s-portable.zip" % VER),
    ("SHA256SUMS.txt", "SHA256SUMS.txt"),
]


def load_mod():
    spec = importlib.util.spec_from_file_location("_gh_release", ROOT / "_gh_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.TOKEN = mod.read_token()
    return mod


def main():
    mod = load_mod()
    rel = mod.api("GET", "/repos/%s/releases/tags/v%s" % (REPO, VER))
    rid = rel["id"]
    old = {a["name"]: a["id"] for a in rel["assets"]}
    print("release id=%s 现有资产: %s" % (rid, ", ".join(old) or "无"))

    print("== 1. 删除旧资产 ==")
    for name, aid in old.items():
        mod.api("DELETE", "/repos/%s/releases/assets/%d" % (REPO, aid))
        print("  deleted:", name)

    print("== 2. 上传新资产 ==")
    for local, asset in ASSETS:
        p = REL / local
        if not p.exists():
            raise SystemExit("缺少 %s" % p)
        mod.upload_asset(REPO, "v" + VER, str(p), asset)
        print("  uploaded:", asset)

    print("== 3. 更新正文 ==")
    body = (REL / ("_release_notes_v%s.md" % VER)).read_text(encoding="utf-8")
    mod.api("PATCH", "/repos/%s/releases/%d" % (REPO, rid),
            {"body": body, "name": "桌面歌词 Desktop-sing v%s" % VER})

    print("== 4. 复核 ==")
    rel2 = mod.api("GET", "/repos/%s/releases/tags/v%s" % (REPO, VER))
    for a in rel2["assets"]:
        print("  %-36s %10d bytes" % (a["name"], a["size"]))
    local_sizes = {a: (REL / l).stat().st_size for l, a in ASSETS}
    ok = all(a["size"] == local_sizes.get(a["name"]) for a in rel2["assets"]) and len(rel2["assets"]) == 3
    print("资产与本地一致:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
