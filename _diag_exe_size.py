# -*- coding: utf-8 -*-
"""看 exe 里到底什么最占地方（按条目大小倒序）

用法：
    .buildenv\\Scripts\\python.exe _diag_exe_size.py dist\\Desktop-sing.exe

单文件 exe 是个 CArchive：里面除了 DLL/字体/数据文件，还嵌一个 PYZ（压缩的
.pyc 集合）。这里把两层都展开，按未压缩大小排序列出 TOP 条目，用来决定
下一步该裁谁 —— 凭印象猜"哪个模块大"很容易裁错方向。
"""
import collections
import os
import sys

from PyInstaller.archive.readers import CArchiveReader


def walk(arc, prefix, out, depth=0):
    """CArchive TOC 的值是 (pos, 压缩长度, 未压缩长度, flag, 类型码)"""
    for name, entry in arc.toc.items():
        pos, dlen, ulen, flag, typecode = entry[:5]
        out.append((prefix + name, ulen, dlen, typecode))
        if typecode == "z" and depth < 2:       # 'z' = 内嵌的 PYZ（.pyc 打包）
            try:
                pyz = arc.open_embedded_archive(name)
                walk(pyz, "%s|" % name, out, depth + 1)
            except Exception as exc:
                print("  ! 展开 %s 失败: %r" % (name, exc))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("dist", "Desktop-sing.exe")
    arc = CArchiveReader(path)
    items = []
    walk(arc, "", items)
    total = sum(s for _, s, _d, _t in items)
    packed = sum(d for _, _s, d, _t in items)
    print("=" * 74)
    print("%s   条目 %d 个" % (os.path.basename(path), len(items)))
    print("  末压缩合计 %.1f MB   压缩后合计 %.1f MB   exe 实际 %.1f MB"
          % (total / 1048576.0, packed / 1048576.0, os.path.getsize(path) / 1048576.0))
    print("=" * 74)
    print("\nTOP 25 单条目（按末压缩大小）：")
    for name, size, dlen, _t in sorted(items, key=lambda x: -x[1])[:25]:
        print("  %8.2f MB -> %7.2f MB  %s" % (size / 1048576.0, dlen / 1048576.0, name))

    # 按顶层目录归并，看"哪一族"占得最多
    agg = collections.Counter()
    aggd = collections.Counter()
    for name, size, dlen, _t in items:
        key = name.split("|")[-1] if "|" in name else name
        parts = key.replace("\\", "/").split("/")
        grp = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
        agg[grp] += size
        aggd[grp] += dlen
    print("\n按目录归并 TOP 15（末压缩 -> 压缩后）：")
    for name, size in agg.most_common(15):
        print("  %8.2f MB -> %7.2f MB  %s" % (size / 1048576.0, aggd[name] / 1048576.0, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
