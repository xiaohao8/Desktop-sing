# -*- coding: utf-8 -*-
"""一次性工具：为 FONT_LIBRARY 各条目计算 sha256 并写回 lyrics_overlay.py。

完整性校验机制（_apply_sec_font.py 已加）是「有 sha256 才校验」——
本工具把各条目的真实哈希算出来填进去，让**线上每个字体都受 sha256 保护**，
任何 CDN/仓库被篡改、网络劫持都会因哈希不符被拒绝（绝不加载来历不明文件）。

用法：
    python _font_sha_updater.py            # 联网计算每个文件的 sha256，写回源码
    python _font_sha_updater.py --check    # 只打印，不改文件
幂等：已带 sha256 的条目跳过计算（除非 --force）。
"""
import argparse
import hashlib
import io
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lyrics_overlay as L

BROWSER_UA = getattr(L, "BROWSER_UA", "Mozilla/5.0")


def _sha256_of_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _fetch_bytes(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def compute_all(force=False):
    results = {}                 # id -> sha256
    for ent in L.FONT_LIBRARY:
        fid = ent["id"]
        if ent.get("sha256") and not force:
            print("skip  %-10s 已有 sha256（--force 覆盖）" % fid)
            results[fid] = ent["sha256"]
            continue
        # 条目可能有多个文件（如 alibaba 有两个），按文件名拼接校验
        blobs = []
        ok = True
        for fname, urls in ent["files"]:
            data = None
            for url in urls:
                try:
                    if not L._font_url_allowed(url):
                        print("!!    %s 的 %s 来源不在白名单，跳过" % (fid, fname))
                        ok = False
                        break
                    data = _fetch_bytes(url)
                    break
                except Exception as ex:
                    print("!!    %s 的 %s 下载失败: %s" % (fid, fname, ex))
            if data is None:
                ok = False
                break
            blobs.append((fname, data))
        if not ok or not blobs:
            print("FAIL  %-10s 无法取得文件" % fid)
            continue
        # 单个文件条目：直接用该文件哈希；多文件：按文件名排序拼起来再哈希
        if len(blobs) == 1:
            sha = _sha256_of_bytes(blobs[0][1])
        else:
            h = hashlib.sha256()
            for fname, data in sorted(blobs, key=lambda x: x[0]):
                h.update(fname.encode("utf-8"))
                h.update(data)
            sha = h.hexdigest()
        results[fid] = sha
        print("ok    %-10s %s" % (fid, sha))
    return results


def write_back(results, dry=False):
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")
    with io.open(src, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    import re
    pat = re.compile(r'(\n\s*)"sha256":\s*"[^"]*",')
    changed = 0
    for ent in L.FONT_LIBRARY:
        fid = ent["id"]
        sha = results.get(fid)
        if not sha:
            continue
        marker = '{"id": "%s",' % fid
        idx = text.find(marker)
        if idx < 0:
            print("!!    找不到条目 %s 的锚点" % fid)
            continue
        fidx = text.find('"files":', idx)
        seg = text[idx:fidx]
        if '"sha256"' in seg:
            # 替换该段内已有的 sha256 值
            new_seg = pat.sub(r'\1"sha256": "%s",' % sha, seg, count=1)
            text = text[:idx] + new_seg + text[fidx:]
        else:
            text = text[:fidx] + ('"sha256": "%s",%s' % (sha, nl)) + text[fidx:]
        changed += 1
    if dry:
        print("（dry-run，未写回；本应将 %d 个条目写回 sha256）" % changed)
        return
    with io.open(src, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("written: %s（%d 个条目）" % (src, changed))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只计算打印，不写回")
    ap.add_argument("--force", action="store_true", help="重算覆盖已有 sha256")
    args = ap.parse_args()
    res = compute_all(force=args.force)
    if args.check:
        write_back(res, dry=True)
    else:
        write_back(res)
    print("完成：%d 个条目" % len(res))


if __name__ == "__main__":
    main()
