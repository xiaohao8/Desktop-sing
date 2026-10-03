# -*- coding: utf-8 -*-
"""变异测试：确认字体下载安全加固的三处断言真的能抓住回归（不是恒真）。

覆盖：
  M1 白名单校验失效   → 外站来源被放行并落盘（test 2 的「外站来源竟然下载成功」/「拒绝来源不应落盘」断言应 FAIL）
  M2 路径穿越防护失效 → ../evil.ttf 被写出 USER_FONT_DIR 之外（test 3 的穿越断言应 FAIL）
  M3 magic 拦截失效  → 非字体文件被交给 addApplicationFont（test 4 的间谍断言应 FAIL）
  M4 sha256 校验失效 → 哈希不符仍被加载（test 5 的「哈希不符竟然通过」断言应 FAIL）

⚠️ 铁律（上一轮血的教训）：一次只注入一处、只改条件/返回值这类最小侵入点，
   绝不删整块代码行。改主文件前先备份；末尾无条件还原。
"""
import io, os, shutil, subprocess, sys

APP = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(APP, "lyrics_overlay.py")
BAK = SRC + ".mutbak"
PY = os.path.join(APP, ".buildenv", "Scripts", "python.exe")

# (名称, 原文, 变异体) —— 每个都只动一个最小片段，把安全闸关掉
MUTANTS = [
    # M1：关掉来源白名单 → 外站字体被下载落盘
    ("M1 白名单校验失效",
     '                if not _font_url_allowed(url):',
     '                if False:  # MUTANT allowlist'),
    # M2：关掉路径穿越防护 → 压缩包内的 ../evil.ttf 照抄写出目录之外
    ("M2 路径穿越防护失效",
     '                            base = os.path.basename(zf.replace("\\\\", "/"))',
     '                            base = zf.replace("\\\\", "/")  # MUTANT traversal'),
    # M3：关掉 magic 头拦截 → 非字体文件被交给 Qt 字体解析器（可能段错误）
    ("M3 magic 拦截失效",
     '    if not _looks_like_font(path):',
     '    if False:  # MUTANT magic'),
    # M4：关掉 sha256 校验 → 被篡改的文件照常加载
    ("M4 sha256 校验失效",
     '                    sha_ok = (not expect_sha) or _sha256_file(tmp) == expect_sha',
     '                    sha_ok = True  # MUTANT sha'),
]

EXPECT_FAIL = {
    "M1 白名单校验失效": "font download security",
    "M2 路径穿越防护失效": "font download security",
    "M3 magic 拦截失效": "font download security",
    "M4 sha256 校验失效": "font download security",
}


def run_smoke():
    try:
        r = subprocess.run([PY, "-u", "smoke_test.py"], cwd=APP,
                           capture_output=True, text=True, encoding="utf-8",
                           timeout=600)
        return r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return "<<TIMEOUT>>"


def fails_in(out):
    names = []
    for ln in out.splitlines():
        if "FAIL-" in ln:
            names.append(ln.split("FAIL-", 1)[1].strip())
    return names


def caught_by(got, group):
    return any(group in g for g in got)


def main():
    if not os.path.exists(BAK):
        shutil.copy2(SRC, BAK)
        print("backup -> %s" % BAK)
    try:
        with io.open(BAK, "r", encoding="utf-8", newline="") as f:
            orig = f.read()
        nl = "\r\n" if "\r\n" in orig else "\n"

        base_out = run_smoke()
        base_fails = fails_in(base_out)
        print("=" * 70)
        print("基线（无变异）失败项：%r" % (base_fails,))
        if base_fails:
            print("基线就不干净，先修基线！")
            return 1
        print("=" * 70)

        allok = True
        for name, old, new in MUTANTS:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            cnt = orig.count(o)
            if cnt != 1:
                print("[%s] FAIL 锚点出现 %d 次（必须恰好 1 次）" % (name, cnt))
                allok = False
                continue
            with io.open(SRC, "w", encoding="utf-8", newline="") as f:
                f.write(orig.replace(o, n, 1))
            out = run_smoke()
            got = fails_in(out)
            caught = caught_by(got, EXPECT_FAIL[name])
            print("[%s] %s  实测失败项=%r" % (
                name, "✓ 断言抓到了" if caught else "✗ 断言恒真！", got))
            if not caught:
                allok = False
            # 还原
            with io.open(SRC, "w", encoding="utf-8", newline="") as f:
                f.write(orig)

        print("=" * 70)
        out = run_smoke()
        got = fails_in(out)
        print("还原后基线失败项：%r" % (got,))
        ok = allok and not got
        print("结论：%s" % ("全部变异都被抓到，还原干净" if ok else "存在漏网或还原失败"))
        return 0 if ok else 1
    finally:
        # 兜底：无论如何都把主文件还原成备份版本，杜绝结构损坏残留
        if os.path.exists(BAK):
            shutil.copy2(BAK, SRC)
            print("[兜底] 已用 .mutbak 还原 lyrics_overlay.py")


if __name__ == "__main__":
    sys.exit(main())
