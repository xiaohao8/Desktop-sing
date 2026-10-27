#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.0.2 一键发布：建 Release + 传三个 ASCII 资产 + 把 2.0.x 标为预发布。

为什么要把 2.0.x 标 pre-release：GitHub 的 `releases/latest` 按语义版本取最高，
2.0.1 > 1.0.2。而本次发版把全渠道版本号统一到 1.0.x（同一套代码重新编号），
不标的话内置更新主源（api .../releases/latest）会把 1.0.2 的用户往回指引到
旧的 2.0.1 构建。预发布版会被 latest 跳过，且下载链接与历史完全保留。

用法：
  python _release_102.py            # 只做事前检查（资产在不在、哈希对不对）
  python _release_102.py --go       # 真发布
"""
import hashlib
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REL = ROOT / "dist" / "release"
REPO = "xiaohao8/Desktop-sing"
VER = "1.0.2"

# 资产名必须纯 ASCII：GitHub 会把非 ASCII 资产名剥成空壳（历史踩过）。
ASSETS = [
    ("桌面歌词-v1.0.2-安装版.exe", "Desktop-sing-v%s-setup.exe" % VER),
    ("桌面歌词-v1.0.2-免安装极速版.zip", "Desktop-sing-v%s-portable.zip" % VER),
    ("SHA256SUMS.txt", "SHA256SUMS.txt"),
]
SUPERSEDED = ["v2.0.1", "v2.0.0"]     # 被 1.0.2 取代编号的旧发布


def _load_gh_release():
    """复用 _gh_release.py 的凭据读取与上传逻辑，避免重复实现。"""
    spec = importlib.util.spec_from_file_location("_gh_release", ROOT / "_gh_release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.TOKEN = mod.read_token()
    return mod


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve(local: str) -> Path:
    p = REL / local
    if not p.exists():
        hits = list(REL.glob("*" + Path(local).suffix))
        raise SystemExit("缺少发布物 %s（同目录现有：%s）"
                         % (p.name, ", ".join(x.name for x in hits)))
    return p


def precheck():
    lines = (REL / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    sums = {ln.split()[1]: ln.split()[0] for ln in lines if ln.strip() and not ln.startswith("#")}
    ok = True
    for local, asset in ASSETS:
        p = resolve(local)
        digest = sha256(p)
        if asset != "SHA256SUMS.txt":
            want = sums.get(p.name, "")
            match = "OK" if want == digest else "MISMATCH %s" % (want or "无记录")
        else:
            match = "清单自身"
        print("%-34s %8.1f MB  %s  %s" % (asset, p.stat().st_size / 1048576, digest[:16], match))
        if match.startswith("MISMATCH"):
            ok = False
    notes = (REL / ("_release_notes_v%s.md" % VER)).read_text(encoding="utf-8")
    print("说明文件 %d 字符，含资产名 setup=%s portable=%s"
          % (len(notes), "Desktop-sing-v1.0.2-setup.exe" in notes,
             "Desktop-sing-v1.0.2-portable.zip" in notes))
    return ok, notes


def mark_prerelease(mod, tag: str):
    rel = mod.api("GET", "/repos/%s/releases/tags/%s" % (REPO, tag))
    if rel.get("prerelease"):
        print("  %s 已是 prerelease，跳过" % tag)
        return
    body = (rel.get("body") or "").strip()
    note = ("\n\n> ⚠️ 该版本已重新编号为 **v%s**（同一套代码，v%s 包含本版本的全部功能与修复）。\n"
            "> 现已标记为预发布，好让 `releases/latest` 与程序内「检查更新」指向 v%s；\n"
            "> 本页面与下载链接依然可用。\n") % (VER, VER, VER)
    mod.api("PATCH", "/repos/%s/releases/%s" % (REPO, rel["id"]),
            {"prerelease": True, "body": body + note})
    print("  %s → prerelease" % tag)


def main():
    go = "--go" in sys.argv
    ok, notes = precheck()
    if not ok:
        print("校验值与清单不一致，中止")
        return 1
    if not go:
        print("\n检查通过。要真发布请加 --go")
        return 0
    mod = _load_gh_release()
    print("\n== 1. 建 Release v%s ==" % VER)
    body_file = REL / ("_release_notes_v%s.md" % VER)
    mod.do_create(REPO, "v" + VER, "桌面歌词 Desktop-sing v%s" % VER, str(body_file),
                  ["%s:%s" % (resolve(l).as_posix(), a) for l, a in ASSETS])
    print("\n== 2. 把旧编号标为预发布 ==")
    for t in SUPERSEDED:
        mark_prerelease(mod, t)
    print("\n== 3. 复核 releases/latest ==")
    latest = mod.api("GET", "/repos/%s/releases/latest" % REPO)
    print("latest =", latest["tag_name"], "|", latest["name"])
    print("assets =", ", ".join(a["name"] for a in latest["assets"]))
    return 0 if latest["tag_name"] == "v" + VER else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
