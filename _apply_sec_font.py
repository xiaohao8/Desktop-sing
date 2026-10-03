# -*- coding: utf-8 -*-
"""安全加固：字体下载来源校验 + 哈希校验 + 解压防护（同前说明）。

实现细节见文件注释。CRLF 安全 + 幂等。
"""
import io
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")

# 插入位置：FONT_MATCH 之前的注释行（唯一）
COMMENT_ANCHOR = "# 已加载族名 → 字体库条目的匹配关键词（字体厂商命名差异大，用关键词兜住）"

ALLOWLIST_BLOCK = '''

# 字体下载来源白名单：只信任这些主机，杜绝任意站点拉文件。
# 注意：ghproxy.net / ghfast.top / mirror.ghproxy.com 是 GitHub 代理，
# 它们把 github.com 的真实文件透传出来（URL 形如
# https://ghproxy.net/https://github.com/...），真实目标是 GitHub，故放行。
# 其他任何主机一律拒绝（含裸 http，防降级劫持）。
FONT_HOST_ALLOWLIST = frozenset([
    "cdn.jsdelivr.net",                # jsDelivr（GitHub 官方源镜像）
    "objects.githubusercontent.com",  # GitHub Release 直链对象存储
    "github.com",                      # 部分 URL 直接走 github.com 原站
    "raw.githubusercontent.com",       # GitHub 原始文件
    "ghproxy.net", "ghfast.top", "mirror.ghproxy.com",  # GitHub 代理
])


def _font_url_allowed(url):
    """字体下载 URL 是否落在白名单内（强制 HTTPS，代理 URL 取真实主机）。"""
    import urllib.parse
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    if p.scheme != "https":            # 裸 http 一律拒绝（防降级劫持）
        return False
    host = (p.netloc or "").lower()
    if host in ("ghproxy.net", "ghfast.top", "mirror.ghproxy.com"):
        inner = p.path.lstrip("/")
        try:
            inner_p = urllib.parse.urlparse(inner)
        except Exception:
            return False
        return inner_p.scheme == "https" and inner_p.netloc.lower() in FONT_HOST_ALLOWLIST
    return host in FONT_HOST_ALLOWLIST


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

'''

# 替换 download_font 里的 for url in urls 循环体与 zip 处理
OLD_DL = '''        dst = os.path.join(USER_FONT_DIR, fname)
        if not (os.path.exists(dst) and os.path.getsize(dst) > 1024):
            tmp = dst + ".part"
            fetched = False
            exc_hint = ""
            for url in urls:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        total = int(r.headers.get("Content-Length") or 0)
                        done = 0
                        with open(tmp, "wb") as f:
                            while True:
                                chunk = r.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                                done += len(chunk)
                                if on_progress:
                                    on_progress(done, total, entry["name"])
                    os.replace(tmp, dst)
                    fetched = True
                    break
                except Exception as ex:
                    exc_hint = "%s: %s" % (url, ex)
                    log("字体镜像失败 %s (%s)" % (fname, url))
                    continue
            if not fetched:
                raise RuntimeError("字体下载失败：%s" % exc_hint)
        if fname.lower().endswith(".zip"):    # 压缩包：挑出字体文件解压
            try:
                with zipfile.ZipFile(dst) as z:
                    for zf in z.namelist():
                        if zf.lower().endswith((".ttf", ".otf")):
                            out = os.path.join(USER_FONT_DIR, os.path.basename(zf))
                            if not os.path.exists(out):
                                with z.open(zf) as src, open(out, "wb") as fp:
                                    fp.write(src.read())
                            families += load_font_file(out)
            except Exception:
                log("字体解压失败:\\n" + traceback.format_exc())'''

NEW_DL = '''        dst = os.path.join(USER_FONT_DIR, fname)
        expect_sha = entry.get("sha256")
        if not (os.path.exists(dst) and os.path.getsize(dst) > 1024):
            tmp = dst + ".part"
            fetched = False
            sha_ok = False
            exc_hint = ""
            for url in urls:
                if not _font_url_allowed(url):
                    exc_hint = "来源不在白名单，已拒绝: %s" % url
                    log("字体来源拒绝 %s (%s)" % (fname, url))
                    continue
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
                    with urllib.request.urlopen(req, timeout=90) as r:
                        total = int(r.headers.get("Content-Length") or 0)
                        done = 0
                        with open(tmp, "wb") as f:
                            while True:
                                chunk = r.read(65536)
                                if not chunk:
                                    break
                                f.write(chunk)
                                done += len(chunk)
                                if on_progress:
                                    on_progress(done, total, entry["name"])
                    sha_ok = (not expect_sha) or _sha256_file(tmp) == expect_sha
                    if not sha_ok:
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                        exc_hint = "sha256 不符，已丢弃: %s" % url
                        log("字体 sha256 不符 %s (%s)" % (fname, url))
                        continue
                    os.replace(tmp, dst)
                    fetched = True
                    break
                except Exception as ex:
                    exc_hint = "%s: %s" % (url, ex)
                    log("字体镜像失败 %s (%s)" % (fname, url))
                    continue
            if not fetched:
                raise RuntimeError("字体下载失败：%s" % exc_hint)
        elif expect_sha and _sha256_file(dst) != expect_sha:
            log("已存在的字体 sha256 不符，删除后重下: %s" % fname)
            try:
                os.remove(dst)
            except OSError:
                pass
            return download_font(entry, on_progress=on_progress)
        if fname.lower().endswith(".zip"):    # 压缩包：挑出字体文件解压
            try:
                with zipfile.ZipFile(dst) as z:
                    for zf in z.namelist():
                        if zf.lower().endswith((".ttf", ".otf")):
                            # 路径穿越防护：只取文件名，绝不照抄压缩包内的相对/绝对路径
                            base = os.path.basename(zf.replace("\\\\", "/"))
                            if not base or base in (".", ".."):
                                continue
                            out = os.path.join(USER_FONT_DIR, base)
                            if os.path.exists(out):
                                families += load_font_file(out)
                                continue
                            with z.open(zf) as src, open(out, "wb") as fp:
                                written = 0
                                # 解压大小上限：防 zip 炸弹（50 MB 字体足够）
                                while written < 50 * 1024 * 1024:
                                    chunk = src.read(65536)
                                    if not chunk:
                                        break
                                    fp.write(chunk)
                                    written += len(chunk)
                                if written >= 50 * 1024 * 1024:
                                    log("字体解压超上限，丢弃: %s" % zf)
                                    try:
                                        os.remove(out)
                                    except OSError:
                                        pass
                                    continue
                            families += load_font_file(out)
            except Exception:
                log("字体解压失败:\\n" + traceback.format_exc())'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    if nl != "\n":
        # 源是 CRLF：所有块里的 \n 必须转成 \r\n
        ALLOWLIST_BLOCK_adj = ALLOWLIST_BLOCK.replace("\n", nl)
        OLD_DL_adj = OLD_DL.replace("\n", nl)
        NEW_DL_adj = NEW_DL.replace("\n", nl)
    else:
        ALLOWLIST_BLOCK_adj, OLD_DL_adj, NEW_DL_adj = ALLOWLIST_BLOCK, OLD_DL, NEW_DL

    # 1) 插入白名单 + 工具函数（在 FONT_MATCH 前）
    if COMMENT_ANCHOR not in src:
        print("FAIL：找不到插入锚点")
        return 1
    if "FONT_HOST_ALLOWLIST" in src:
        print("skip  白名单（已应用）")
    else:
        idx = src.index(COMMENT_ANCHOR)
        src = src[:idx] + ALLOWLIST_BLOCK_adj + src[idx:]
        print("ok    插入字体下载白名单 + 校验函数")

    # 2) 替换下载/解压逻辑
    if NEW_DL_adj in src:
        print("skip  下载解压加固（已应用）")
    elif src.count(OLD_DL_adj) != 1:
        print("FAIL：下载解压锚点出现 %d 次" % src.count(OLD_DL_adj))
        return 1
    else:
        src = src.replace(OLD_DL_adj, NEW_DL_adj, 1)
        print("ok    下载前校验 + 解压加固")

    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("written: %s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
