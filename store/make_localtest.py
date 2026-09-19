# -*- coding: utf-8 -*-
"""生成「本地实测版 MSIX」：自签一份已签名副本，让本机真的装得上。

背景（2026-09-19 实测确立）
--------------------------
- **未签名的 MSIX 装不上**。提审包必须保持未签名（微软拿到后自己重签），
  所以本地想看真实效果，只能自己签一份**副本**来装，绝不能动 `store/out/` 根目录
  那份 —— 它既是上传物，也被自检 `P5.20c4` 盯着（根目录只许有一个 .msix）。
- **证书 Subject 必须等于清单里的 Publisher（`CN=…`）**，逐字符一致。
  这样副本与原包的 Package Family Name 完全相同 → 装起来会真的进
  **STORE_MODE（商店模式）**，看到的才是商店版的界面裁剪。
- **⚠️ 只认机器级证书库**：AppX 部署服务以 SYSTEM 运行，
  导入到 `Cert:\\CurrentUser\\TrustedPeople` / `CurrentUser\\Root` **完全无效**
  （实测照样报 0x800B0109「根证书不受信任」）。证书必须进
  **LocalMachine**，而那需要管理员。用户级那条路不用再试。
- ⚠️ 测完请 `UNINSTALL.cmd` 卸载 —— 它跟商店正式版共用同一个 PFN，
  留着装可能影响将来从商店安装正式版。

用法
----
    .buildenv\\Scripts\\python.exe store\\make_localtest.py          # 生成 + 签名
    .buildenv\\Scripts\\python.exe store\\make_localtest.py --fmt    # 同上，但重新签发证书
    .buildenv\\Scripts\\python.exe store\\make_localtest.py --open   # 做完打开产物目录

产物落在 `store/out/dev/localtest/`：
    Desktop-sing-<版本>-localtest.msix   已签名，可装
    local-test.cer                       公钥（管理员导入本机信任用）
    local-test.pfx / .key.pem            私钥（仅本机测试，勿外传）
"""

import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OUT = os.path.join(ROOT, "store", "out")
WORK = os.path.join(OUT, "dev", "localtest")

CER = os.path.join(WORK, "local-test.cer")          # DER，导入信任用
CER_PEM = os.path.join(WORK, "local-test.cer.pem")
KEY_PEM = os.path.join(WORK, "local-test.key.pem")
PFX = os.path.join(WORK, "local-test.pfx")
PFX_PWD = "desktopsing"                             # 仅本机测试，安全性无关紧要


def die(msg):
    print("[FATAL] " + msg)
    sys.exit(1)


def load_publisher():
    p = os.path.join(ROOT, "store", "identity.local.json")
    if not os.path.isfile(p):
        die("缺 store/identity.local.json —— 没有真实 Publisher 就签不出能在本机"
            "冒充商店版的证书（Subject 必须逐字符等于清单 Publisher）")
    try:
        with open(p, encoding="utf-8") as f:
            ident = json.load(f)
    except Exception as ex:                                  # noqa: BLE001
        die("identity.local.json 解析失败：%s" % ex)
    pub = str(ident.get("publisher") or "").strip()
    if not pub or not pub.startswith("CN=") or "PLACEHOLDER" in pub:
        die("identity.local.json 里的 publisher 还是占位值：%r" % pub)
    return pub


def newest_msix():
    cand = glob.glob(os.path.join(OUT, "*.msix"))
    if not cand:
        die("store/out/ 里还没有 .msix —— 先跑 build_store.py 出一个")
    return max(cand, key=os.path.getmtime)


def find_signtool():
    globbed = sorted(glob.glob(
        r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe"))
    if globbed:
        return globbed[-1]                     # 取版本号最高的那一套
    return None


def run(cmd, **kw):
    print("       $ " + " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def cert_matches(publisher):
    """现有证书的 Subject 是否与 Publisher 逐字符一致 —— 一致才复用，否则重签一份。

    ⚠️ 别用「子串包含」来判断：openssl 输出的各版本格式不统一（有的会在 `=` 两边
    加空格），而且 publisher 里含多个 `-` 分隔段，子串匹配极容易误判成不匹配，
    结果每次都重新签发证书（私钥白白报废、本机信任过的旧证书也白留在凭证库里）。
    """
    if not os.path.isfile(CER_PEM):
        return False
    r = run(["openssl", "x509", "-in", CER_PEM, "-noout", "-subject"])
    if r.returncode != 0:
        return False
    # 形如 "subject=CN=815AB3D3-C7A7-40CB-93F0-57D02D5FAAF0"，去空格后比较
    got = r.stdout.strip().replace(" ", "").split("subject=", 1)[-1]
    want = publisher.strip().replace(" ", "")
    return got == want


def make_cert(subject):
    print("[2/4] 生成自签测试证书（Subject 必须与清单 Publisher 逐字符一致）")
    print("       %s" % subject)
    os.makedirs(WORK, exist_ok=True)
    for f in (CER, CER_PEM, KEY_PEM, PFX):
        if os.path.isfile(f):
            os.remove(f)

    r = run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", KEY_PEM, "-out", CER_PEM, "-days", "3650",
             "-subj", "/" + subject,
             "-addext", "keyUsage=critical,digitalSignature",
             "-addext", "extendedKeyUsage=codeSigning",
             "-addext", "basicConstraints=critical,CA:FALSE",
             "-sha256"])
    if r.returncode != 0:
        die("openssl 生成证书失败：\n%s\n%s" % (r.stdout, r.stderr))

    # 私钥用途受限于代码签名、且 CA:FALSE，本机测试用足够，风险可控
    r = run(["openssl", "pkcs12", "-export", "-macalg", "sha256",
             "-out", PFX, "-inkey", KEY_PEM, "-in", CER_PEM,
             "-name", "Desktop-sing LocalTest", "-passout", "pass:" + PFX_PWD])
    if r.returncode != 0:
        die("导出 PFX 失败：\n%s\n%s" % (r.stdout, r.stderr))

    r = run(["openssl", "x509", "-in", CER_PEM, "-inform", "PEM",
             "-out", CER, "-outform", "DER"])
    if r.returncode != 0:
        die("转 DER 失败：\n%s\n%s" % (r.stdout, r.stderr))
    print("       OK -> %s" % CER)


def main():
    print("=" * 64)
    print("本地实测版 MSIX（自签，用于真机看商店版效果）")
    print("=" * 64)

    pub = load_publisher()
    src = newest_msix()
    st = find_signtool()
    if not st:
        die("找不到 signtool.exe —— 需要 Windows SDK")

    print("[1/4] 源包 : %s" % os.path.relpath(src, ROOT))
    print("      Publisher : %s" % pub)
    print("      signtool  : %s" % st)

    os.makedirs(WORK, exist_ok=True)
    force = "--fmt" in sys.argv
    if force or not cert_matches(pub):
        make_cert(pub)
    else:
        print("[2/4] 复用已有证书（Subject 与 Publisher 逐字符一致）")

    basename = os.path.basename(src).replace(".msix", "-localtest.msix")
    dst = os.path.join(WORK, basename)
    print("[3/4] 复制一份再签名 —— 绝不动上传包本身")
    shutil.copy2(src, dst)
    print("       %s -> %s" % (os.path.relpath(src, ROOT), os.path.relpath(dst, ROOT)))

    print("[4/4] 签名")
    r = run([st, "sign", "/fd", "SHA256", "/f", PFX, "/p", PFX_PWD,
             "/d", "Desktop-sing LocalTest", dst])
    if r.returncode != 0:
        die("signtool 失败：\n%s\n%s" % (r.stdout, r.stderr))
    print("       OK")

    print("")
    print("=" * 64)
    print("产物就绪：%s" % WORK)
    print("=" * 64)
    print("""
接下来（需要**一次**管理员，弹 UAC 点「是」）：

    certutil -addstore -f TrustedPeople "%s"
    certutil -addstore -f Root          "%s"
    Add-AppxPackage -Path "%s"

⚠️ 必须用机器级证书库。用户级（certutil -addstore -user …）无效 ——
   AppX 部署服务以 SYSTEM 运行，只认 LocalMachine，实测用户级照样 0x800B0109。

装好后：先在播放器里播一首歌（Edge/Chrome 放视频也算，走 SMTC），
        再从开始菜单打开「桌面歌词」，或看托盘图标。

测完务必卸载，它与商店正式版共用 PFN：
    Get-AppxPackage -Name A135C2AE.Desktop-sing | Remove-AppxPackage
""" % (CER, CER, dst))

    if "--open" in sys.argv:
        os.startfile(WORK)                                    # noqa: S606


if __name__ == "__main__":
    main()
