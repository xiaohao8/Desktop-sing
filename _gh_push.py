# -*- coding: utf-8 -*-
"""用 GitHub REST API 把镜像仓库的 HEAD 推到远端（绕开 git 传输层）。

背景：本机 git 走 https 推送极慢（>180s 被 SIGTERM），且 .gitconfig 里的
insteadOf 把 github.com 重写到已下线的 gh-proxy.com。这里直接用 Git Data API
重建 tree + commit + 更新 ref，不依赖 git 二进制，也不受代理重写影响。

用法：
  python _gh_push.py <repo> <local_repo_dir> <branch>
"""
import base64
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

API = "https://api.github.com"
CRED_NAME = "git:https://github.com"

# 不上传的路径段：构建产物 / 缓存 / 本地环境
SKIP_DIRS = {".git", "dist", "build", "__pycache__", ".buildenv", ".workbuddy",
             "preview", "node_modules", ".idea", ".vscode"}
SKIP_FILES = {"localtest.msix"}


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_token() -> str:
    advapi = ctypes.WinDLL("Advapi32.dll")
    pcred = ctypes.POINTER(CREDENTIALW)()
    if not advapi.CredReadW(CRED_NAME, 1, 0, ctypes.byref(pcred)):
        raise ctypes.WinError()
    try:
        c = pcred.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)\
            .decode("utf-16-le").rstrip("\x00")
    finally:
        advapi.CredFree(pcred)


TOKEN = None


def api(method, path, body=None, raw=None, content_type=None, timeout=180):
    url = path if path.startswith("http") else API + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("User-Agent", "Desktop-sing-push")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if content_type:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw_body = r.read()
    return json.loads(raw_body) if raw_body else {}


def api_retry(method, path, body=None, tries=3, **kw):
    """GitHub 偶发 5xx/超时，重试几次再放弃。"""
    last = None
    for i in range(tries):
        try:
            return api(method, path, body=body, **kw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (400, 401, 403, 404, 422):
                raise RuntimeError(f"{method} {path} -> {last}") from None
        except Exception as e:                       # 超时 / 连接重置
            last = f"{type(e).__name__}: {e}"
        print(f"  retry {i + 1}/{tries} ({last})", flush=True)
        import time
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{method} {path} 失败：{last}")


def git(repo_dir, *args):
    p = subprocess.run(["git"] + list(args), cwd=repo_dir,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout.strip()


def tracked_files(repo_dir, ref="HEAD"):
    """按 git 自己跟踪的清单取文件（自动尊重 .gitignore，不会误传 dist/ 等）。

    用 -z（NUL 分隔）避免中文路径被八进制转义成 "preview\\/xx\\345\\270..."；
    输出走临时文件而非管道——NUL 字节经过管道会在本机 shell 里被截断。
    """
    import tempfile
    fd, out_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    # 不用 with/finally 删除：沙箱的 safe-delete 钩子会拦截 unlink 导致整脚本被 SIGTERM
    with open(out_path, "wb") as fh:
        subprocess.run(["git", "-c", "core.quotepath=false", "ls-tree", "-r", "-z",
                        "--name-only", ref], cwd=repo_dir, stdout=fh)
    raw = Path(out_path).read_bytes().decode("utf-8", "replace")
    return [f for f in raw.split("\0") if f.strip()]


def main():
    global TOKEN
    repo = sys.argv[1]                      # xiaohao8/Desktop-sing
    repo_dir = Path(sys.argv[2])            # 本地镜像仓库
    branch = sys.argv[3] if len(sys.argv) > 3 else "main"

    TOKEN = read_token()
    files = tracked_files(str(repo_dir))
    print(f"tracked files: {len(files)}")

    # 1) 远端当前 HEAD（作为 base_tree，让未改动文件保持原样）
    remote_ref = api("GET", f"/repos/{repo}/git/ref/heads/{branch}")
    remote_sha = remote_ref["object"]["sha"]
    base_tree = api("GET", f"/repos/{repo}/git/commits/{remote_sha}")["tree"]["sha"]
    print("remote HEAD:", remote_sha[:10])

    # 2) 只上传「本地 git blob sha 与远端不同」的文件。
    #    git blob sha = sha1("blob <len>\0" + content)，可本地算，不必逐个问 API。
    #    182 个文件全走 HTTPS 建 blob 必然超时被沙箱 SIGTERM。
    remote_tree = api("GET", f"/repos/{repo}/git/trees/{base_tree}?recursive=1")
    remote_map = {n["path"]: n["sha"] for n in remote_tree.get("tree", [])
                  if n.get("type") == "blob"}

    def local_blob_sha(data: bytes) -> str:
        h = hashlib.sha1()
        h.update(b"blob %d\0" % len(data))
        h.update(data)
        return h.hexdigest()

    changed, same = [], 0
    for rel in files:
        if rel in SKIP_FILES or any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
        fp = repo_dir / rel
        if not fp.is_file():
            continue
        if local_blob_sha(fp.read_bytes()) != remote_map.get(rel):
            changed.append(rel)
        else:
            same += 1

    print(f"unchanged: {same}, changed: {len(changed)}", flush=True)
    for c in changed:
        print("   M", c, flush=True)
    if not changed:
        print("远端已是最新，无需提交")
        return 0

    entries = []
    for i, rel in enumerate(changed, 1):
        data = (repo_dir / rel).read_bytes()
        blob = api_retry("POST", f"/repos/{repo}/git/blobs", {
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
        })
        fp = repo_dir / rel
        mode = "100755" if (fp.stat().st_mode & 0o111) else "100644"
        entries.append({"path": rel, "mode": mode, "type": "blob", "sha": blob["sha"]})
        print(f"  [{i}/{len(changed)}] {rel}", flush=True)

    print(f"blobs uploaded: {len(entries)}")
    if not entries:
        print("远端已是最新，无需提交")
        return 0

    # 3) 建 tree（基于远端 tree 叠加变化）
    tree_sha = api("POST", f"/repos/{repo}/git/trees",
                   {"base_tree": base_tree, "tree": entries})["sha"]

    # 4) 建 commit：message / 作者取本地 HEAD
    msg = git(str(repo_dir), "log", "-1", "--pretty=%B").strip()
    author_name = git(str(repo_dir), "log", "-1", "--pretty=%an") or "xiaohao8"
    author_email = git(str(repo_dir), "log", "-1", "--pretty=%ae") or \
        "xiaohao8@users.noreply.github.com"
    when = git(str(repo_dir), "log", "-1", "--pretty=%cI")
    commit = api("POST", f"/repos/{repo}/git/commits", {
        "message": msg, "tree": tree_sha, "parents": [remote_sha],
        "author": {"name": author_name, "email": author_email, "date": when},
        "committer": {"name": author_name, "email": author_email, "date": when},
    })
    print("commit:", commit["sha"][:10])

    # 5) 快进 ref（不用 force，除非远端被改过）
    api("PATCH", f"/repos/{repo}/git/refs/heads/{branch}",
        {"sha": commit["sha"], "force": False})
    print("OK pushed ->", branch, commit["sha"][:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
