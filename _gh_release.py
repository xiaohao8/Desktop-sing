# -*- coding: utf-8 -*-
"""创建 GitHub Release 并上传发布物（资产名强制 ASCII）。

背景见 _gh_push.py：git 传输层在本机极慢，改走 REST API。
两个必须遵守的坑：
  1) asset 名**必须纯 ASCII**——中文名会被 GitHub 服务端剥成空壳（有前车之鉴）；
  2) 大文件（30~40MB）上传要给足超时，且 GitHub 单资产上限 2GB。

用法：
  python _gh_release.py create <repo> <tag> <name> <body_file> <asset_path>[:asset_name] ...
  python _gh_release.py list   <repo>
"""
import base64
import ctypes
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from ctypes import wintypes
from pathlib import Path

API = "https://api.github.com"
CRED_NAME = "git:https://github.com"


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


def api(method, path, body=None, timeout=180):
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN)
    req.add_header("User-Agent", "Desktop-sing-release")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def is_ascii(name: str) -> bool:
    return all(ord(c) < 128 for c in name)


def upload_asset(repo, tag, path, asset_name=None, tries=3):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    name = asset_name or p.name
    if not is_ascii(name):
        raise ValueError(f"asset 名必须纯 ASCII（GitHub 会把非 ASCII 名剥成空壳）：{name}")

    rel = api("GET", f"/repos/{repo}/releases/tags/{tag}")
    # 同名资产已存在就先删掉，避免 422
    for a in rel.get("assets", []):
        if a["name"] == name:
            print(f"  删除已存在的同名资产 {name}", flush=True)
            api("DELETE", f"/repos/{repo}/releases/assets/{a['id']}")

    upload_url = rel["upload_url"].split("{")[0]
    data = p.read_bytes()
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    print(f"  上传 {name}（{len(data) / 1048576:.1f} MB）…", flush=True)

    last = None
    for i in range(tries):
        try:
            # 资产名必须放在 upload_url 的 ?name= 查询参数里；
            # 只放进 body 或 header 都会拿到 400 "Invalid name for request"。
            url = upload_url + "?name=" + urllib.parse.quote(name)
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Authorization", "Bearer " + TOKEN)
            req.add_header("Content-Type", ctype)
            req.add_header("User-Agent", "Desktop-sing-release")
            with urllib.request.urlopen(req, timeout=900) as r:
                out = json.loads(r.read())
            print(f"  ✓ {out['name']}  {out['size']} bytes", flush=True)
            print(f"    {out['browser_download_url']}", flush=True)
            return out
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        print(f"  重试 {i + 1}/{tries}（{last}）", flush=True)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"上传 {name} 失败：{last}")


def do_create(repo, tag, name, body_file, assets):
    body = Path(body_file).read_text(encoding="utf-8") if body_file else ""
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": False,
    }
    try:
        rel = api("POST", f"/repos/{repo}/releases", payload)
        print("created release:", rel["html_url"], flush=True)
    except urllib.error.HTTPError as e:
        if e.code == 422:                      # 已存在就复用
            print("release 已存在，复用", flush=True)
            rel = api("GET", f"/repos/{repo}/releases/tags/{tag}")
        else:
            raise
    for spec in assets:
        # "路径:资产名" 语法。Windows 盘符也带冒号，所以不能只按最后一个冒号切——
        # 改成「切开后左边确实是个存在的文件」才认定是给了资产名。
        path, asset_name = spec, None
        if ":" in spec:
            head, tail = spec.rsplit(":", 1)
            if tail and "/" not in tail and "\\" not in tail and Path(head).exists():
                path, asset_name = head, tail
        upload_asset(repo, tag, path, asset_name)
    print("\nRelease 页面：", rel["html_url"], flush=True)
    return 0


def do_list(repo):
    for r in api("GET", f"/repos/{repo}/releases?per_page=20"):
        print(f"{r['tag_name']:<12} {r['name']}")
        for a in r.get("assets", []):
            print(f"    {a['name']:<42} {a['size'] / 1048576:>7.1f} MB")
    return 0


if __name__ == "__main__":
    import urllib.parse
    TOKEN = read_token()
    cmd = sys.argv[1]
    if cmd == "create":
        # create <repo> <tag> <name> <body_file> [asset ...]
        rc = do_create(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6:])
    elif cmd == "list":
        rc = do_list(sys.argv[2])
    else:
        print(__doc__)
        rc = 2
    sys.exit(rc)
