# -*- coding: utf-8 -*-
"""发布签名与完整性校验工具。

设计取舍：**没有证书也能用**。没配证书时一切检查照跑、签名自动跳过（退出码 0），
因此可以直接挂在构建后面当常规步骤；等哪天买了证书，设几个环境变量就能原地签上。

    python sign_release.py                  # 默认 --check：算 SHA256 + 报签名状态 + 写 SHA256SUMS.txt
    python sign_release.py --sign           # 签名 dist/release 下所有 exe/zip（有证书才真签）
    python sign_release.py --check --sign   # 先签再核对

签名所需环境变量（**都不要在命令行里写密码，用系统环境变量或本机凭据保管**）：
    SIGN_PFX          PFX/PKCS#12 文件路径（与 SIGN_PWD 配套使用）
    SIGN_PWD          PFX 密码；若证书在 USB token 里可留空，届时交互输入
    SIGN_THUMBPRINT   二选一：用证书存储里的指纹（配合可选 SIGN_STORE，默认 My）
    SIGN_TIMESTAMP    RFC3161 时间戳服务，默认 http://timestamp.digicert.com
    SIGN_DESC / SIGN_URL   签名描述与产品主页（可选）
    SIGN_TOOL         signtool.exe 路径（不设则自动在本机 Windows SDK 里找）
"""
import ctypes
import fnmatch
import glob
import hashlib
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
RELEASE = os.path.join(BASE, "dist", "release")
ONEDIR_EXE = os.path.join(BASE, "dist", "Desktop-sing-v1.0.0", "Desktop-sing.exe")
SUMS = os.path.join(RELEASE, "SHA256SUMS.txt")

PATTERNS = ("*.exe", "*.zip")

# 只有这些扩展名存在 Authenticode 签名概念
_SIGNED_EXTS = (".exe", ".dll", ".msi", ".sys")


def dw(s):
    """控制台里的显示宽度：中日韩字符按 2 列宽算，否则表格对不齐。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def align(s, width):
    return s + " " * max(1, width - dw(s))


# ---------------------------------------------------------------- 目标收集
def collect_targets():
    files = []
    if os.path.isdir(RELEASE):
        for name in sorted(os.listdir(RELEASE)):
            if any(fnmatch.fnmatch(name, p) for p in PATTERNS):
                files.append(os.path.join(RELEASE, name))
    if os.path.isfile(ONEDIR_EXE):
        files.append(ONEDIR_EXE)
    return files


def sha256(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------- Authenticode 签名状态
# 直接调 WinVerifyTrust：不依赖 PowerShell，也不用装额外包。
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


class WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [("cbStruct", ctypes.c_ulong),
                ("pcwszFilePath", ctypes.c_wchar_p),
                ("hFile", ctypes.c_void_p),
                ("pgKnownSubject", ctypes.c_void_p)]


class WINTRUST_DATA(ctypes.Structure):
    _fields_ = [("cbStruct", ctypes.c_ulong),
                ("pPolicyCallbackData", ctypes.c_void_p),
                ("pSIPClientData", ctypes.c_void_p),
                ("dwUIChoice", ctypes.c_ulong),
                ("fdwRevocationChecks", ctypes.c_ulong),
                ("dwUnionChoice", ctypes.c_ulong),
                ("pFile", ctypes.c_void_p),
                ("dwStateAction", ctypes.c_ulong),
                ("hWVTStateData", ctypes.c_void_p),
                ("pwszURLReference", ctypes.c_wchar_p),
                ("dwProvFlags", ctypes.c_ulong),
                ("dwUIContext", ctypes.c_ulong),
                ("pSignatureSettings", ctypes.c_void_p)]


WINTRUST_ACTION_GENERIC_VERIFY_V2 = GUID(
    0xAAC56B, 0xCD44, 0x11D0, (0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))

# TRUST_E_NOSIGNATURE：这一族统一按「未签名」解释
_ERR_TEXT = {
    0x00000000: "已签名 · 校验通过",
    0x800B0100: "未签名",
    0x800B0101: "签名无效 / 已损坏",
    0x800B0109: "证书链不受信任（多为自签证书）",
    0x800B010A: "证书已吊销",
    0x800B010B: "证书已过期",
    0x80096010: "数字签名校验失败",
    0x80070002: "文件不存在",
}


def signature_info(path):
    """返回 (码, 说明)。码 0 表示签名有效。"""
    file_info = WINTRUST_FILE_INFO(ctypes.sizeof(WINTRUST_FILE_INFO), path, None, None)
    data = WINTRUST_DATA()
    data.cbStruct = ctypes.sizeof(WINTRUST_DATA)
    data.dwUIChoice = 2            # WTD_UI_NONE
    data.fdwRevocationChecks = 0   # WTD_REVOKE_NONE
    data.dwUnionChoice = 1         # WTD_CHOICE_FILE
    data.pFile = ctypes.cast(ctypes.pointer(file_info), ctypes.c_void_p)
    data.dwStateAction = 1         # WTD_STATEACTION_VERIFY
    try:
        code = ctypes.WinDLL("wintrust").WinVerifyTrust(
            0, ctypes.byref(WINTRUST_ACTION_GENERIC_VERIFY_V2), ctypes.byref(data))
        # 收尾：释放校验过程里分配的句柄
        data.dwStateAction = 2     # WTD_STATEACTION_CLOSE
        ctypes.WinDLL("wintrust").WinVerifyTrust(
            0, ctypes.byref(WINTRUST_ACTION_GENERIC_VERIFY_V2), ctypes.byref(data))
    except Exception as ex:        # 非 Windows / 老版本 API
        return -1, "无法校验（%s）" % ex
    # ctypes 默认按有符号 int 收返回值，0x800B0100 会变成负数，统一转回无符号便于比对
    code &= 0xFFFFFFFF
    return code, _ERR_TEXT.get(code, "未知状态 0x%08X" % code)


# ------------------------------------------------------------------ 签名
def find_signtool():
    env = os.environ.get("SIGN_TOOL", "").strip()
    if env and os.path.isfile(env):
        return env
    found = __import__("shutil").which("signtool")
    if found:
        return found
    cands = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe"))
    return cands[-1] if cands else ""


def cert_config():
    """返回 (签名参数片段, 来源说明)；没有可用凭据时返回 (None, 原因)。"""
    pfx = os.environ.get("SIGN_PFX", "").strip()
    thumb = os.environ.get("SIGN_THUMBPRINT", "").strip()
    if thumb:
        return ["-sha1", thumb,
                "-sm" if os.environ.get("SIGN_MACHINE_STORE") else "-s",
                os.environ.get("SIGN_STORE", "My")], "证书存储指纹 %s…" % thumb[:8]
    if pfx and os.path.isfile(pfx):
        return ["-f", pfx, "-p", os.environ.get("SIGN_PWD", "")], "PFX 文件 %s" % os.path.basename(pfx)
    if pfx:
        return None, "SIGN_PFX 指向的文件不存在：%s" % pfx
    return None, "未配置证书凭据"


def sign_files(files):
    tool = find_signtool()
    if not tool:
        print("[跳过] 本机没找到 signtool.exe（装 Windows SDK 或设 SIGN_TOOL 指向它）")
        return True
    cert, src = cert_config()
    if cert is None:
        print("[跳过] 未签名：%s" % src)
        print("       配 SIGN_PFX+SIGN_PWD 或 SIGN_THUMBPRINT 后重跑本脚本即可签名。")
        return True
    ts = os.environ.get("SIGN_TIMESTAMP", "http://timestamp.digicert.com").strip()
    common = [tool, "sign", "/fd", "sha256", "/tr", ts, "/td", "sha256",
              "/d", os.environ.get("SIGN_DESC", "桌面歌词 Desktop-sing")]
    url = os.environ.get("SIGN_URL", "").strip()
    if url:
        common += ["/du", url]
    ok = True
    for f in files:
        cmd = common + cert + [f]
        shown = " ".join('"****"' if (i > 0 and cmd[i - 1] == "-p") else x for i, x in enumerate(cmd))
        print("  → %s" % shown)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            print("     OK %s" % os.path.basename(f))
        else:
            ok = False
            print("     FAIL %s\n%s" % (os.path.basename(f), (r.stdout or r.stderr)[:600]))
    print("[签名] 证书来源：%s" % src)
    return ok


# ------------------------------------------------------------------ 校验
def check_files(files, write_sums=True):
    rows, signed, unsigned, broken = [], 0, 0, 0
    for f in files:
        if not os.path.isfile(f):
            continue
        # 只有 PE / MSI 才有 Authenticode 概念；zip 之类的 WinVerifyTrust 会直接返回
        # TRUST_E_SUBJECT_FORM_UNKNOWN(0x800B0003)，那是「不适用」而非「坏了」
        if os.path.splitext(f)[1].lower() in _SIGNED_EXTS:
            code, text = signature_info(f)
            if code == 0:
                signed += 1
            elif code == 0x800B0100:      # TRUST_E_NOSIGNATURE
                unsigned += 1
            elif code is not None:
                broken += 1
        else:
            code, text = None, "—（压缩包，只看校验值）"
        rows.append((os.path.basename(f), os.path.getsize(f), sha256(f), code, text))
    width = max(dw(r[0]) for r in rows) if rows else 10
    print(align("文件", width) + "  " +
          align("SHA256（前 32 位）", 34) + "签名状态")
    print("-" * (width + 60))
    for name, size, digest, code, text in rows:
        print(align(name, width) + "  " + align(digest[:32], 34) + text)
    if write_sums and rows:
        os.makedirs(RELEASE, exist_ok=True)
        with open(SUMS, "w", encoding="utf-8") as fp:
            for name, _size, digest, _c, _t in rows:
                fp.write("%s  %s\n" % (digest, name))
        print("\n已写出校验值清单：%s" % SUMS)
        print("核对命令：certutil -hashfile <文件> SHA256")
    other = len(rows) - signed - unsigned - broken   # 压缩包等不适用签名的文件
    print("\n签名有效 %d · 未签名 %d · 不适用签名 %d · 签名异常 %d"
          % (signed, unsigned, other, broken))
    if unsigned:
        print("注：未签名属当前预期状态（尚未配代码签名证书），不算失败；")
        print("    Windows 首次运行会弹 SmartScreen，放行步骤见 README「发布与安全」。")
    return broken == 0


def main():
    args = set(sys.argv[1:])
    files = collect_targets()
    if not files:
        raise SystemExit("没找到可处理的文件：先跑 build_exe.py / pkg_portable.py / NSIS")
    ok = True
    if "--sign" in args:
        print("== 签名 ==")
        ok = sign_files([f for f in files if os.path.isfile(f)]) and ok
    if "--check" in args or "--sign" not in args:
        print("== 完整性校验 ==")
        ok = check_files(files) and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
