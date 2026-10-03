# -*- coding: utf-8 -*-
"""给冒烟测试加第四轮第四组：font_download_security。

固化三项安全加固：
  1. 字体来源白名单：白名单外主机 / 裸 http / 代理嵌套非白名单 一律拒绝；
     合法 URL（jsdelivr / github release / 代理透传 github）放行。
  2. 来源不在白名单 → download_font 抛 RuntimeError，绝不落盘。
  3. 解压路径穿越防护 + 非字体文件不喂 Qt（防段错误）；zip 解压大小上限。
幂等 + CRLF 安全。
"""
import io
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.py")
MARK = 'check("font download security", font_download_security)'
ANCHOR = 'check("config atomic write", config_atomic_write)'


def _fake_http_factory(by_prefix):
    """桩：按 URL 前缀返回 BytesIO，其余抛错；兼容 Request 对象与 with。"""
    import urllib.request
    real = urllib.request.urlopen

    def fake(req, timeout=90):
        url = req.full_url if hasattr(req, "full_url") else req
        for pref, data in by_prefix.items():
            if url.startswith(pref):
                from io import BytesIO

                class _R:
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

    return fake, real


BLOCK = '''

import zipfile as _zip

def font_download_security():
    """字体下载安全加固：来源白名单 / 路径穿越 / 非字体不喂 Qt"""
    import tempfile as _tf
    from PySide6.QtCore import QObject as _QObject
    fails = []

    def ck(cond, why):
        if not cond:
            fails.append(why)

    real = L.urllib.request.urlopen

    def run(entry, by_prefix, udir):
        fh, _ = _fake_http_factory(by_prefix)
        L.urllib.request.urlopen = fh
        prev = L.USER_FONT_DIR
        L.USER_FONT_DIR = udir
        try:
            return L.download_font(entry)
        finally:
            L.urllib.request.urlopen = real
            L.USER_FONT_DIR = prev

    # 1) 白名单判定
    ck(L._font_url_allowed("https://cdn.jsdelivr.net/gh/x/y.ttf"),
       "jsdelivr 应放行")
    ck(L._font_url_allowed("https://github.com/x/releases/download/v/A.ttf"),
       "github release 应放行")
    ck(L._font_url_allowed("https://ghproxy.net/https://github.com/x/y.ttf"),
       "代理透传 github 应放行")
    ck(not L._font_url_allowed("http://cdn.jsdelivr.net/gh/x/y.ttf"),
       "裸 http 应拒绝")
    ck(not L._font_url_allowed("https://evil.example.com/x.ttf"),
       "任意外站应拒绝")
    ck(not L._font_url_allowed("https://ghproxy.net/https://evil.example.com/x.ttf"),
       "代理嵌套非白名单应拒绝")

    # 2) 来源不在白名单 → 抛错、不落盘
    d = _tf.mkdtemp(prefix="ds_fsec_")
    with open(os.path.join(d, "keep.txt"), "w") as f:
        f.write("x")
    try:
        entry = {"id": "x", "name": "测试", "files": [
            ("font.ttf", ["https://evil.example.com/font.ttf"])]}
        try:
            run(entry, {"https://evil.example.com/font.ttf": b"BYTES"}, d)
            ck(False, "外站来源竟然下载成功")
        except RuntimeError as ex:
            ck("不在白名单" in str(ex), "外站来源应被拒绝: " + str(ex))
        ck(not os.path.exists(os.path.join(d, "font.ttf")),
           "拒绝来源不应落盘文件")
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)

    # 3) 路径穿越 + 非字体不喂 Qt（防段错误）
    d = _tf.mkdtemp(prefix="ds_fsec2_")
    import io as _io
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("../evil.ttf", b"X" * 1024)
        z.writestr("good.ttf", b"G" * 2048)        # 无 magic，非字体
    buf.seek(0)
    try:
        entry = {"id": "z", "name": "z", "zip": True, "files": [
            ("bundle.zip", ["https://github.com/x/bundle.zip"])]}
        fams = run(entry, {"https://github.com/x/bundle.zip": buf.getvalue()}, d)
        evil = os.path.normpath(os.path.join(d, "..", "evil.ttf"))
        ck(not os.path.exists(evil), "路径穿越文件不应被写出: " + evil)
        ck(os.path.exists(os.path.join(d, "good.ttf")),
           "合法文件名应被解压到 fonts 目录")
        ck(isinstance(fams, list) and not fams,
           "非字体被 magic 校验拦截，返回空而非崩溃")
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)

    for w in fails:
        check("font download security",
              lambda w=w: (_ for _ in ()).throw(AssertionError(w)))
    return True


check("font download security", font_download_security)
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if MARK in src:
        print("skip：第四组已存在")
        return 0
    nl = "\r\n" if "\r\n" in src else "\n"
    anchor = ANCHOR.replace("\n", nl)
    block = BLOCK.replace("\n", nl)
    if src.count(anchor) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(anchor))
        return 1
    src = src.replace(anchor, anchor + block, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("written: %s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
