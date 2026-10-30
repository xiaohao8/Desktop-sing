#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.0.3 一键发布：建 Release + 传三个 ASCII 资产。

1.0.3 是 1.0.x 线上的正常递增，语义上大于 1.0.2，GitHub `releases/latest`
会自动指过来；此前被标 prerelease 的 v2.0.x 不用再动，也没有需要标预发布的旧编号。

用法：
  python _release_103.py            # 只做事前检查（资产在不在、哈希对不对）
  python _release_103.py --go       # 真发布
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REL = ROOT / "dist" / "release"
REPO = "xiaohao8/Desktop-sing"
VER = "1.0.3"

# 资产名必须纯 ASCII：GitHub 会把非 ASCII 资产名剥成空壳（历史踩过）。
ASSETS = [
    ("桌面歌词-v1.0.3-安装版.exe", "Desktop-sing-v%s-setup.exe" % VER),
    ("桌面歌词-v1.0.3-免安装极速版.zip", "Desktop-sing-v%s-portable.zip" % VER),
    ("SHA256SUMS.txt", "SHA256SUMS.txt"),
]


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
          % (len(notes), "Desktop-sing-v1.0.3-setup.exe" in notes,
             "Desktop-sing-v1.0.3-portable.zip" in notes))
    return ok, notes


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
    print("\n== 2. 复核 releases/latest ==")
    latest = mod.api("GET", "/repos/%s/releases/latest" % REPO)
    print("latest =", latest["tag_name"], "|", latest["name"])
    print("assets =", ", ".join(a["name"] for a in latest["assets"]))
    return 0 if latest["tag_name"] == "v" + VER else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
