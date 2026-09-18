# -*- coding: utf-8 -*-
"""读 exe 的版本信息资源，确认 OriginalFilename / InternalName / ProductName 等。"""
import ctypes
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    exe = os.path.join(BASE, "dist", "Desktop-sing-v1.0.0", "Desktop-sing.exe")
    if len(sys.argv) > 1:
        exe = sys.argv[1]
    if not os.path.isfile(exe):
        raise SystemExit("exe 不存在: %s" % exe)

    ver = ctypes.WinDLL("version")
    size = ver.GetFileVersionInfoSizeW(exe, None)
    if not size:
        raise SystemExit("无版本信息")
    buf = ctypes.create_string_buffer(size)
    ver.GetFileVersionInfoW(exe, 0, size, buf)
    # \VarFileInfo\Translation 取语言/代码页
    trans = ctypes.c_void_p()
    tlen = ctypes.c_uint()
    if not ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation",
                              ctypes.byref(trans), ctypes.byref(tlen)):
        raise SystemExit("读 Translation 失败")
    lang = ctypes.cast(trans, ctypes.POINTER(ctypes.c_ushort))[0]
    cp = ctypes.cast(trans, ctypes.POINTER(ctypes.c_ushort))[1]
    root = "\\StringFileInfo\\%04x%04x" % (lang, cp)
    keys = ["CompanyName", "FileDescription", "FileVersion", "InternalName",
            "LegalCopyright", "OriginalFilename", "ProductName", "ProductVersion"]
    for k in keys:
        p = ctypes.c_void_p()
        ln = ctypes.c_uint()
        if ver.VerQueryValueW(buf, "%s\\%s" % (root, k),
                               ctypes.byref(p), ctypes.byref(ln)):
            val = ctypes.wstring_at(p, ln.value - 1) if ln.value else ""
            print("%-16s : %s" % (k, val))
        else:
            print("%-16s : (缺失)" % k)


if __name__ == "__main__":
    main()
