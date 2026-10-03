# -*- coding: utf-8 -*-
"""变异测试：确认第四轮新断言真的能抓住回归（不是恒真）。

⚠️ 铁律（上一轮血的教训）：一次只注入一处、只改条件/返回值这类最小侵入点，
   绝不删整块代码行（删 for 循环首行会破坏缩进结构，导致无法还原）。
   改主文件前先备份。
"""
import io, os, shutil, subprocess, sys

APP = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(APP, "lyrics_overlay.py")
BAK = SRC + ".mutbak"
PY = os.path.join(APP, ".buildenv", "Scripts", "python.exe")

# (名称, 原文, 变异体) —— 每个都只动一个最小片段
MUTANTS = [
    # M1：还原「停止播放不作废」——第一组断言应 FAIL
    ("M1 停止时不递增 _req_id",
     "            self._req_id += 1\n            self.song = None",
     "            # self._req_id += 1   # MUTANT\n            self.song = None"),
    # M2：还原「等封面再 emit」——第二组断言应 FAIL（歌词上屏被拖住）
    # ⚠️ 锚点要跟当前代码一致：守卫（cover_pix is None）是后补的，
    # 写旧版锚点会 0 次命中、变异被静默跳过（第一次跑就踩了）。
    ("M2 回到先下封面再 emit",
     "            self.fetched.emit((req_id, lines or [], words or {},\n"
     "                               None, trans or [], bool(singer_ok)))\n",
     "            _cv = None\n"
     "            if cover_url and self._req_id == req_id and self.cover_pix is None:\n"
     "                try:\n"
     "                    _cv = http_get(cover_url, timeout=5)\n"
     "                except Exception:\n"
     "                    _cv = None\n"
     "            self.fetched.emit((req_id, lines or [], words or {},\n"
     "                               _cv, trans or [], bool(singer_ok)))\n"),
    # M3：_on_cover_ready 去掉 req_id 校验 —— 过期封面/停止后采纳
    ("M3 cover_ready 不校验 req_id",
     "        if req_id != self._req_id or self.song is None or self.cover_pix is not None:\n"
     "            return",
     "        if self.cover_pix is not None:\n"
     "            return"),
    # M4：_on_cover_ready 允许覆盖已有封面
    ("M4 cover_ready 无条件覆盖",
     "        if req_id != self._req_id or self.song is None or self.cover_pix is not None:\n"
     "            return",
     "        if req_id != self._req_id or self.song is None:\n"
     "            return"),
    # M5：_apply_cover_bytes 加载失败也返回 True（判据分辨力检查）
    ("M5 _apply_cover_bytes 恒真",
     "        if not data or not pix.loadFromData(data):\n            return False",
     "        if not data:\n            return False"),
    # M6：拆掉「已有封面不重复下载」守卫 → 冒烟里新增断言应 FAIL
    ("M6 已有封面仍重复下载",
     "            if cover_url and self._req_id == req_id and self.cover_pix is None:",
     "            if cover_url:"),
    # M7：还原「直接截断写」→ 写入中途留下半截配置，原子性断言应 FAIL
    ("M7 回到直接截断写",
     "    tmp = \"%s.tmp\" % CONFIG_PATH\n",
     "    tmp = CONFIG_PATH\n"),
    # M8：_salvage_json 抛异常 → 抢救能力应 FAIL
    ("M8 salvage 整体失效",
     "    out = {}\n"
     "    dec = json.JSONDecoder()\n"
     "    # save_config 固定 indent=2",
     "    return {}\n"
     "    out = {}\n"
     "    dec = json.JSONDecoder()\n"
     "    # save_config 固定 indent=2"),
]
# 注：原先的 M9「删掉 startswith 判断」是**等价变异体** —— 紧跟其后的
# `q = line.find('"', 1); if q <= 0: continue` 已经覆盖了同样的输入
# （引号不成对时 find 返回 -1，照样跳过）。已改为直接清掉那行冗余判断
# （_add_smoke4d.py），让代码里不留「看起来有判据、实则无作用」的分支。

EXPECT_FAIL = {
    "M1 停止时不递增 _req_id": "stale fetch guard",
    "M2 回到先下封面再 emit": "async fetch ordering",
    "M3 cover_ready 不校验 req_id": "async fetch ordering",
    "M4 cover_ready 无条件覆盖": "async fetch ordering",
    "M5 _apply_cover_bytes 恒真": "async fetch ordering",
    "M6 已有封面仍重复下载": "async fetch ordering",
    "M7 回到直接截断写": "config atomic write",
    "M8 salvage 整体失效": "config atomic write",
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
    # 只取 "FAIL-" 后面那段名字（去掉缩进和前缀），判定时做**子串**匹配：
    # 一个变异可能同时触发同一组的多个断言（列表会重复出现该名字）。
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
    base_out = run_smoke()
    base_fails = fails_in(base_out)
    print("=" * 70)
    print("基线（无变异）失败项：%r" % (base_fails,))
    if base_fails:
        print("基线就不干净，先修基线！")
        return 1
    print("=" * 70)

    with io.open(BAK, "r", encoding="utf-8", newline="") as f:
        orig = f.read()
    nl = "\r\n" if "\r\n" in orig else "\n"

    allok = True
    for name, old, new in MUTANTS:
        o, n = old.replace("\n", nl), new.replace("\n", nl)
        if orig.count(o) != 1:
            print("[%s] FAIL 锚点出现 %d 次" % (name, orig.count(o)))
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


if __name__ == "__main__":
    sys.exit(main())
