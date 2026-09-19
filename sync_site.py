#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把主仓库的 site/ 同步到站点部署仓库（xiaohao8/music）。

站点的**源文件在主仓库的 `site/`**；部署副本在单独仓库里给 Netlify 用。
两边必须逐字节（换行归一化后）一致，否则"改了官网却没上线"这种事故会静默发生。

用法：
    python sync_site.py                     # 预览：只报告两边差异，不写任何文件
    python sync_site.py --apply             # 真的把 site/ 覆盖到部署仓库
    python sync_site.py --check             # 只校验（同默认），有漂移则退出码 1，可挂进 CI/自检
    python sync_site.py --apply --push      # 同步后自动 commit + push 部署仓库
    python sync_site.py --dst <路径>         # 指定部署仓库工作副本位置

设计要点：
- **只同步 `site/` 里的文件**；部署仓库里的 README.md / netlify.toml / .gitignore
  属于该仓库自己的元数据，不在同步范围，也不会被当成"多余文件"报错（见 LOCAL_KEEP）。
- **文本文件统一写成 LF**：本机全局 `core.autocrlf=input`，提交时 CRLF 会被转成 LF，
  如果工作副本留着 CRLF，两边"看起来"就差一截。写入时直接归一化，比对也按归一化后比。
- 二进制（png/ico 等）原样复制，不做任何转换。
- 默认不写文件，只报告 —— 想真同步必须显式 `--apply`。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, "site")

#: 部署仓库工作副本的默认位置（可用 --dst 覆盖）
DEFAULT_DST = os.path.normpath(
    os.path.join(ROOT, "..", "..", "..", "Documents", "GitHub", "music")
)

#: 部署仓库里**不属于 site/** 的文件：它们是该仓库自己的元数据，允许存在、不参与同步
LOCAL_KEEP = {"README.md", "netlify.toml", ".gitignore"}

#: 这些扩展名按文本处理（写入时把 CRLF 归一化为 LF）；其余按二进制原样复制
TEXT_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".jsx", ".ts", ".json",
            ".svg", ".txt", ".md", ".py", ".toml", ".yml", ".yaml", ".xml"}

#: 不参与同步的目录/文件（构建残留、编辑器垃圾）
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache", ".buildenv", "dist", "build"}
IGNORE_FILES = {"Thumbs.db", "desktop.ini", ".DS_Store"}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def norm_bytes(data: bytes, path: str) -> bytes:
    """文本文件把 CRLF 归一化为 LF；二进制原样返回。"""
    if os.path.splitext(path)[1].lower() in TEXT_EXT:
        return data.replace(b"\r\n", b"\n")
    return data


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def walk_files(base: str) -> dict[str, str]:
    """返回 {相对路径: 绝对路径}，跳过 IGNORE_*。"""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name in IGNORE_FILES:
                continue
            abs_p = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_p, base).replace("\\", "/")
            out[rel] = abs_p
    return out


def read_norm(abs_p: str) -> bytes:
    with open(abs_p, "rb") as fh:
        return norm_bytes(fh.read(), abs_p)


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n / 1:.1f} {unit}"
        n /= 1024.0
    return f"{n} B"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def collect(src_dir: str, dst_dir: str):
    """比对两边，返回 (待写入/更新, 内容相同, 部署仓库多余文件, 源缺失目标)。"""
    src = walk_files(src_dir)
    dst = walk_files(dst_dir)

    to_write: list[tuple[str, str, str]] = []   # (rel, 原因, 备注)
    same: list[str] = []
    missing_in_dst: list[str] = []

    for rel, abs_src in sorted(src.items()):
        s_bytes = read_norm(abs_src)
        abs_dst = os.path.join(dst_dir, rel.replace("/", os.sep))
        if rel not in dst:
            to_write.append((rel, "新增", f"{fmt_size(len(s_bytes))}"))
            continue
        d_bytes = read_norm(dst[rel])
        if sha(s_bytes) != sha(d_bytes):
            to_write.append((rel, "更新", f"{len(s_bytes)}B -> {len(d_bytes)}B"))
        else:
            same.append(rel)

    extra: list[str] = []
    for rel in sorted(dst):
        if rel in src:
            continue
        # 部署仓库自己的元数据不算多余
        if rel in LOCAL_KEEP:
            continue
        extra.append(rel)

    for rel in sorted(src):
        if rel not in dst and rel not in {w[0] for w in to_write}:
            missing_in_dst.append(rel)

    return src, dst, to_write, same, extra


def do_apply(src_dir: str, dst_dir: str, items: list[tuple[str, str, str]]) -> list[str]:
    """把 items 里的文件按归一化内容写入部署仓库，返回写过的相对路径。"""
    written: list[str] = []
    for rel, _reason, _note in items:
        abs_src = os.path.join(src_dir, rel.replace("/", os.sep))
        abs_dst = os.path.join(dst_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
        data = read_norm(abs_src)
        with open(abs_dst, "wb") as fh:
            fh.write(data)
        written.append(rel)
    return written


def git(dst_dir: str, *args: str) -> int:
    cmd = ["git", "-C", dst_dir, *args]
    print("  $ " + " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="把主仓库 site/ 同步到站点部署仓库（默认只报告，不改文件）",
    )
    ap.add_argument("--dst", default=DEFAULT_DST,
                    help=f"部署仓库工作副本路径（默认 {DEFAULT_DST}）")
    ap.add_argument("--apply", action="store_true",
                    help="真的写入部署仓库（不加此参数只做差异报告）")
    ap.add_argument("--push", action="store_true",
                    help="同步后自动 git add/commit/push（隐含 --apply 的写入结果）")
    ap.add_argument("--check", action="store_true",
                    help="只校验一致性；有漂移时退出码 1（适合挂进自检）")
    args = ap.parse_args()

    src_dir = SRC_DIR
    dst_dir = os.path.abspath(args.dst)

    print("=" * 68)
    print("站点同步 site/ -> 部署仓库")
    print("  源  :", src_dir)
    print("  目标:", dst_dir)
    print("=" * 68)

    if not os.path.isdir(src_dir):
        print(f"[FAIL] 源目录不存在：{src_dir}")
        return 2
    if not os.path.isdir(dst_dir):
        print(f"[FAIL] 目标目录不存在：{dst_dir}")
        print("       先把部署仓库 clone 下来，或用 --dst 指定位置。")
        return 2

    src, dst, to_write, same, extra = collect(src_dir, dst_dir)

    print(f"\n源文件 {len(src)} 个｜目标文件 {len(dst)} 个")
    print(f"  内容一致 : {len(same)}")
    print(f"  需要同步 : {len(to_write)}")
    for rel, reason, note in to_write:
        print(f"      [{reason}] {rel}  ({note})")
    if extra:
        print(f"  目标独有 : {len(extra)}（不在 site/ 里，未参与同步）")
        for rel in extra:
            print(f"      [-] {rel}")

    drift = bool(to_write) or bool(extra)

    if args.check and not args.apply:
        print()
        if drift:
            print("[FAIL] 两边不一致：部署仓库与主仓库 site/ 有漂移。")
            print("       修法：跑 `python sync_site.py --apply` 同步（源永远以主仓库 site/ 为准）。")
            return 1
        print("[ OK ] 部署仓库与主仓库 site/ 完全一致。")
        return 0

    if not args.apply:
        print()
        if drift:
            print("预览模式：没有写入任何文件。要真同步请加 --apply")
        else:
            print("两边已一致，无需写入。")
        return 0

    if not to_write:
        print("\n没有需要写入的文件。")

    written = do_apply(src_dir, dst_dir, to_write) if to_write else []
    if written:
        print(f"\n已写入 {len(written)} 个文件（文本按 LF 归一化）。")

    # 写完复查：源与目标必须逐字节（归一化后）一致，防止半截写入
    print("\n复查一致性 ...")
    _, _, again, _, extra2 = collect(src_dir, dst_dir)
    if again or extra2:
        print("[FAIL] 复查不通过，仍有差异：")
        for rel, reason, note in again:
            print(f"       [{reason}] {rel} ({note})")
        for rel in extra2:
            print(f"       [-] {rel}")
        return 1
    print(f"[ OK ] 复查通过：{len(src)} 个文件全部一致。")

    if args.push:
        print("\n提交并推送部署仓库 ...")
        rc = git(dst_dir, "add", "-A")
        if rc != 0:
            print("[FAIL] git add 失败"); return rc
        rc = git(dst_dir, "status", "--short")
        if rc != 0:
            print("[FAIL] git status 失败"); return rc
        rc = git(dst_dir, "commit", "-m", "同步官网与隐私政策（源：Desktop-sing/site）")
        if rc != 0:
            print("[WARN] 没有可提交的改动，或提交失败（若确实无需提交属正常）。")
        rc = git(dst_dir, "push", "origin", "HEAD")
        if rc != 0:
            print("[FAIL] git push 失败（网络/鉴权问题），改动已在本地提交，稍后重试 push 即可。")
            return rc
        print("[ OK ] 已推送到部署仓库。")

    print("\n完成。Netlify 会自动重新部署（无构建步骤，直接发布仓库根目录）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
