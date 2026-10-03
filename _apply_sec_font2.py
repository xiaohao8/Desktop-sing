# -*- coding: utf-8 -*-
"""加固：load_font_file 加字体文件头 magic 校验，避免把坏文件喂给 Qt 触发段错误。

实测发现：QFontDatabase.addApplicationFont 对损坏/伪造的字体文件会在 C++ 层
**直接进程崩溃**（segfault，Python try 抓不到）。任何途径落到 %APPDATA%/Desktop-sing/
fonts 里的坏文件（下载被截断、zip 解压出错、用户手放）都会让程序一启动就崩。

修法：加载前先校验文件头 magic（TrueType/OpenType/WOFF），不合法直接返回 []，
绝不调 Qt。CRLF 安全 + 幂等。
"""
import io
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")

OLD = '''def load_font_file(path: str) -> list:
    """加载单个字体文件，返回其中的族名列表"""
    try:
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            return []
        return list(QFontDatabase.applicationFontFamilies(fid))
    except Exception:
        log("字体加载失败 %s:\\n%s" % (path, traceback.format_exc()))
        return []
'''

NEW = '''_FONT_MAGIC = (b"\\x00\\x01\\x00\\x00", b"OTTO", b"ttcf", b"wOFF", b"wOF2")


def _looks_like_font(path: str) -> bool:
    """轻量文件头校验：避免把损坏/伪造的文件喂给 Qt 字体解析器。

    QFontDatabase.addApplicationFont 对坏文件会在 C++ 层直接进程崩溃
    （segfault，Python try 抓不到）。任何落到 fonts/ 目录的坏文件
    （下载截断、zip 解压出错、用户手放）都会让程序一启动就崩。
    只认 TrueType / OpenType(CFF) / TTC / WOFF 的 magic 头即可挡住绝大部分。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return False
    if len(head) < 4:
        return False
    return any(head.startswith(m) for m in _FONT_MAGIC)


def load_font_file(path: str) -> list:
    """加载单个字体文件，返回其中的族名列表

    加载前先校验文件头 magic：坏文件直接跳过，绝不交给 Qt（避免 segfault）。
    """
    if not _looks_like_font(path):
        log("跳过非字体文件（magic 不符）: %s" % os.path.basename(path))
        return []
    try:
        fid = QFontDatabase.addApplicationFont(path)
        if fid < 0:
            return []
        return list(QFontDatabase.applicationFontFamilies(fid))
    except Exception:
        log("字体加载失败 %s:\\n%s" % (path, traceback.format_exc()))
        return []
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    old, new = OLD.replace("\n", nl), NEW.replace("\n", nl)
    if new in src:
        print("skip：magic 校验已应用")
        return 0
    if src.count(old) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(old))
        return 1
    src = src.replace(old, new, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("ok：load_font_file 加 magic 校验")
    return 0


if __name__ == "__main__":
    sys.exit(main())
