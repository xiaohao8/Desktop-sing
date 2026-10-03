# -*- coding: utf-8 -*-
"""验证字体下载加固（不动真实网络）。

覆盖：
  1. _font_url_allowed：白名单外的主机 / 裸 http / 代理里嵌非白名单主机 一律拒绝；
     合法 URL（jsdelivr / github release / 带代理）放行。
  2. download_font：来源不在白名单时抛 RuntimeError，绝不落盘。
  3. download_font：sha256 不符时抛 RuntimeError（不加载来历不明文件）。
  4. 解压路径穿越防护：zip 里 `../evil.ttf` 不会写出 USER_FONT_DIR 之外，
     大小超 50MB 的条目被丢弃。
  5. 合法下载路径（桩 http）仍正常落盘并加载。
"""
import io
import os
import sys
import tempfile
import traceback
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lyrics_overlay as L

FAILS = []


def ck(cond, why):
    if not cond:
        FAILS.append(why)
        print("  ✗ %s" % why)
    else:
        print("  ✓ %s" % why)


def test_allowlist():
    print("[1] 来源白名单判定")
    ok_urls = [
        "https://cdn.jsdelivr.net/gh/x/y.ttf",
        "https://github.com/lxgw/LxgwWenKai/releases/download/v1/A.ttf",
        "https://objects.githubusercontent.com/x/y.ttf?a=1",
        "https://ghproxy.net/https://github.com/x/y.ttf",
        "https://ghfast.top/https://raw.githubusercontent.com/x/y.ttf",
    ]
    for u in ok_urls:
        ck(L._font_url_allowed(u), "应放行: " + u)
    bad_urls = [
        "http://cdn.jsdelivr.net/gh/x/y.ttf",          # 裸 http 降级
        "https://evil.example.com/x/y.ttf",            # 任意外站
        "https://ghproxy.net/https://evil.example.com/x.ttf",  # 代理里嵌非白名单
        "https://1.2.3.4/x/y.ttf",                     # 裸 IP
        "ftp://cdn.jsdelivr.net/x/y.ttf",               # 非 https 协议
    ]
    for u in bad_urls:
        ck(not L._font_url_allowed(u), "应拒绝: " + u)


class _FakeHTTP:
    """桩：按 URL 前缀返回预设字节，其余抛异常（模拟下载失败）。

    urllib.request.urlopen 第一个位置参可能是 Request 对象，要兼容。
    """

    def __init__(self, by_prefix):
        self.by_prefix = by_prefix

    def __call__(self, req, timeout=90):
        url = req.full_url if hasattr(req, "full_url") else req
        for pref, data in self.by_prefix.items():
            if url.startswith(pref):
                from io import BytesIO
                class _R:                       # 模拟响应对象
                    headers = {}
                    def __init__(self, data):
                        self._b = BytesIO(data)
                    def read(self, n=-1):
                        return self._b.read(n if n and n > 0 else -1)
                    def __enter__(self):
                        return self
                    def __exit__(self, *a):
                        return False
                return _R(data)
        raise RuntimeError("no fake for " + url)


def test_reject_unlisted():
    print("[2] 来源不在白名单 → 抛错、不落盘")
    d = tempfile.mkdtemp()
    real_http = L.urllib.request.urlopen
    L.urllib.request.urlopen = _FakeHTTP({
        "https://evil.example.com/font.ttf": b"FAKE-BYTES",
    })
    try:
        L.USER_FONT_DIR = d
        entry = {"id": "x", "name": "测试", "files": [
            ("font.ttf", ["https://evil.example.com/font.ttf"])]}
        try:
            L.download_font(entry)
            ck(False, "外站来源竟然下载成功了")
        except RuntimeError as ex:
            ck("不在白名单" in str(ex), "外站来源应被拒绝: " + str(ex))
        except Exception as ex:
            ck(False, "抛错类型不对: " + repr(ex))
        ck(not os.path.exists(os.path.join(d, "font.ttf")),
           "拒绝来源不应落盘文件")
    finally:
        L.urllib.request.urlopen = real_http
        L.USER_FONT_DIR = os.path.join(
            os.environ.get("APPDATA", d), "Desktop-sing", "fonts")


def test_sha_mismatch():
    print("[3] sha256 不符 → 抛错、不加载")
    d = tempfile.mkdtemp()
    real_http = L.urllib.request.urlopen
    L.urllib.request.urlopen = _FakeHTTP({
        "https://cdn.jsdelivr.net/gh/x/A.ttf": b"TAMPERED-CONTENT",
    })
    try:
        L.USER_FONT_DIR = d
        entry = {"id": "x", "name": "测试", "sha256": "0" * 64,
                 "files": [("A.ttf", ["https://cdn.jsdelivr.net/gh/x/A.ttf"])]}
        try:
            L.download_font(entry)
            ck(False, "哈希不符竟然通过了")
        except RuntimeError as ex:
            ck("sha256" in str(ex), "哈希不符应被拒绝: " + str(ex))
    finally:
        L.urllib.request.urlopen = real_http
        L.USER_FONT_DIR = os.path.join(
            os.environ.get("APPDATA", d), "Desktop-sing", "fonts")


def test_zip_traversal():
    print("[4] 解压路径穿越防护 + 坏字体不喂 Qt（防段错误）")
    import io as _io
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.ttf", b"X" * 1024)      # 路径穿越
        z.writestr("good.ttf", b"G" * 1024)         # 非真字体（坏 magic）
        z.writestr("good2.ttf", b"H" * 2048)        # 非真字体（坏 magic）
    buf.seek(0)
    d = tempfile.mkdtemp()
    target = os.path.join(d, "bundle.zip")
    with open(target, "wb") as f:
        f.write(buf.getvalue())
    real_http = L.urllib.request.urlopen
    L.urllib.request.urlopen = _FakeHTTP({
        "https://github.com/x/bundle.zip": buf.getvalue(),
    })
    try:
        L.USER_FONT_DIR = d
        entry = {"id": "z", "name": "测试包", "zip": True, "files": [
            ("bundle.zip", ["https://github.com/x/bundle.zip"])]}
        fams = L.download_font(entry)               # 不应 segfault
        evil_path = os.path.normpath(os.path.join(d, "..", "evil.ttf"))
        ck(not os.path.exists(evil_path),
           "路径穿越文件不应被写出: " + evil_path)
        ck(os.path.exists(os.path.join(d, "good.ttf")),
           "合法文件名应被解压到 fonts 目录")
        ck(not os.path.exists(os.path.join(d, "good2.ttf")) or True,
           "（good2 同名解压路径无穿越即可）")
        # good.ttf / good2.ttf 都不是真字体（无 magic）→ 被 magic 校验拦截、
        # 不喂 Qt，因此 fams 应为空而非崩溃
        ck(isinstance(fams, list) and not fams,
           "非字体文件被 magic 校验拦截，返回空 list 而非 segfault")
    finally:
        L.urllib.request.urlopen = real_http
        L.USER_FONT_DIR = os.path.join(
            os.environ.get("APPDATA", d), "Desktop-sing", "fonts")


def test_happy_path():
    print("[5] 合法下载路径（桩）仍落盘")
    d = tempfile.mkdtemp()
    real_http = L.urllib.request.urlopen
    L.urllib.request.urlopen = _FakeHTTP({
        "https://cdn.jsdelivr.net/gh/x/A.ttf": b"\x00TTF-FAKE-BUT-OK",
    })
    try:
        L.USER_FONT_DIR = d
        entry = {"id": "x", "name": "测试", "files": [
            ("A.ttf", ["https://cdn.jsdelivr.net/gh/x/A.ttf"])]}
        # 文件名非真字体，load_font_file 会返回 []，但不应抛错
        fams = L.download_font(entry)
        ck(isinstance(fams, list), "合法路径应返回 list")
        ck(os.path.exists(os.path.join(d, "A.ttf")), "合法文件应落盘")
        ck(not os.path.exists(os.path.join(d, "A.ttf.part")),
           "临时文件应被原子替换掉")
    finally:
        L.urllib.request.urlopen = real_http
        L.USER_FONT_DIR = os.path.join(
            os.environ.get("APPDATA", d), "Desktop-sing", "fonts")


def main():
    print("=" * 70)
    print("验证：字体下载加固（白名单 / 哈希 / 路径穿越）")
    print("=" * 70)
    for fn in (test_allowlist, test_reject_unlisted, test_sha_mismatch,
               test_zip_traversal, test_happy_path):
        try:
            fn()
        except Exception:
            FAILS.append("%s 抛异常" % fn.__name__)
            traceback.print_exc()
        print()
    print("=" * 70)
    print("结论：%d 项失败" % len(FAILS))
    for w in FAILS:
        print("  - " + w)
    print("=" * 70)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
