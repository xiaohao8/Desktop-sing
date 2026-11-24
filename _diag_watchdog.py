# -*- coding: utf-8 -*-
"""原生 watchdog（tools/watchdog.c）端到端验证。

三段测试，全部在本进程内完成验证与清理，不依赖交互式桌面会话：
  1) 监视模式：--watch-pid 盯一个活进程 → 写 supervisor.pid；写停机哨兵 → 退出并清文件
  2) 拉起模式：无参数 → 拉起同目录的「Desktop-sing.exe」（用 python.exe 假扮，
     无 stdin 立即退出 code 0）→ 守护进程识别正常退出后收工
  3) 真机集成：拉起冻结主程序 → 守护进程应为其常驻（内存 < 8MB，远低于
     Python 版的 ~55MB）→ 哨兵 + 结束主程序 → 守护进程收工

用法：.buildenv312\\Scripts\\python.exe _diag_watchdog.py
"""
import os
import ctypes
import ctypes.wintypes as wintypes
import glob
import shutil
import subprocess
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import lyrics_overlay as L                                    # noqa: E402

CFG = L.CFG_DIR
PID_FILE = os.path.join(CFG, "supervisor.pid")
SENTINEL = os.path.join(CFG, "keepalive.off")
WD = os.path.join(BASE, "tools", "watchdog.exe")
DETACHED = 0x00000008 | 0x08000000 | 0x00000200   # DETACHED|NO_WINDOW|NEW_GROUP

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("  %-4s %s%s" % ("PASS" if ok else "FAIL", name,
                           ("  — " + detail) if detail else ""))


def _run_text(args):
    """tasklist 等系统命令输出为 OEM/GBK 编码，按字节抓回再解"""
    out = subprocess.run(args, capture_output=True).stdout
    for enc in ("gbk", "utf-8"):
        try:
            return out.decode(enc)
        except UnicodeDecodeError:
            continue
    return out.decode("utf-8", "replace")


def wd_pids():
    """tasklist 里所有 watchdog.exe 的 (pid, 内存KB)"""
    out = _run_text(["tasklist", "/FO", "CSV"])
    pids = []
    for line in out.splitlines():
        if "watchdog.exe" in line.lower():
            parts = [p.strip('"') for p in line.split('","')]
            pids.append((int(parts[1]), parts[-1].replace('"', "").replace(" K", "")))
    return pids


def proc_alive(pid):
    return L._pid_alive(int(pid))


class _PMC_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def mem_private_kb(pid):
    """进程**私有内存**（KB）。⚠️ 别用 tasklist 的「内存使用」——那是工作集，
    含共享 DLL 页（原生 watchdog 实测工作集 ~9.2MB、私有仅 ~2.0MB），拿它卡
    8MB 阈值会把正常程序判成 FAIL（2026-11-11 自测踩到）。"""
    h = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, int(pid))
    if not h:
        return None
    try:
        c = _PMC_EX()
        c.cb = ctypes.sizeof(_PMC_EX)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return None
        return c.PrivateUsage / 1024
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def wait_no_wd(timeout=8.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not wd_pids():
            return True
        time.sleep(0.4)
    return False


# ---------------------------------------------------------------- 1) 监视模式
print("[0] 清理残留守护进程")
subprocess.run(["taskkill", "/F", "/IM", "watchdog.exe"], capture_output=True)
time.sleep(0.5)
print("[1] 监视模式（--watch-pid）")
sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                           creationflags=DETACHED)
try:
    wd = subprocess.Popen([WD, "--watch-pid", str(sleeper.pid)],
                          creationflags=DETACHED)
    time.sleep(2.0)
    pids = wd_pids()
    check("守护进程常驻", len(pids) == 1, str(pids))
    pid_in_file = ""
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            pid_in_file = f.read().strip()
    except OSError:
        pass
    check("supervisor.pid 已写且为守护进程自身", pid_in_file.isdigit() and
          any(int(pid_in_file) == p for p, _m in pids),
          "file=%s pids=%s" % (pid_in_file, [p for p, _m in pids]))
    # 哨兵生效：写哨兵 → 守护进程退出并清理 pid 文件
    with open(SENTINEL, "w") as f:
        f.write(str(int(time.time())))
    check("哨兵后退出 + 清理 pid 文件",
          wait_no_wd() and not os.path.exists(PID_FILE))
finally:
    sleeper.kill()
    try:
        os.remove(SENTINEL)
    except OSError:
        pass

# ---------------------------------------------------------------- 2) 拉起模式
print("[2] 拉起模式（假主程序 + 两种退出码）")
tmp = tempfile.mkdtemp(prefix="wd_test_")
try:
    shutil.copy2(WD, os.path.join(tmp, "watchdog.exe"))
    # 2a) 假主程序 = hostname.exe（无参数打印主机名后退出码 0）
    #     → 守护进程应识别「正常退出」并收工
    hostname = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                            "System32", "hostname.exe")
    shutil.copy2(hostname, os.path.join(tmp, "Desktop-sing.exe"))
    subprocess.Popen([os.path.join(tmp, "watchdog.exe")],
                     creationflags=DETACHED, cwd=tmp)
    check("2a 子进程 exit 0 → 守护进程收工", wait_no_wd(15))

    # 2b) 假主程序 = ping.exe（无参数用法错误、退出码 1）
    #     → 守护进程应保持重拉循环（退避），直到哨兵出现才收工
    ping = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                        "System32", "ping.exe")
    shutil.copy2(ping, os.path.join(tmp, "Desktop-sing.exe"))
    wd = subprocess.Popen([os.path.join(tmp, "watchdog.exe")],
                          creationflags=DETACHED, cwd=tmp)
    time.sleep(5.0)                      # 覆盖 ≥1 轮「拉起→秒退→退避」
    still = wd_pids()
    check("2b 子进程异常退出 → 守护进程保持重拉", len(still) >= 1, str(still))
    with open(SENTINEL, "w") as f:
        f.write(str(int(time.time())))
    check("2b 哨兵后退出 + 清理 pid 文件",
          wait_no_wd(10) and not os.path.exists(PID_FILE))
finally:
    subprocess.run(["taskkill", "/F", "/IM", "watchdog.exe"], capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        os.remove(SENTINEL)
    except OSError:
        pass

# ---------------------------------------------------------------- 3) 真机集成
print("[3] 真机集成（冻结主程序 + 原生守护进程）")
# ⚠️ 别写死版本目录：写死 v2.0.1 时换到 2.0.2 后本项会**静默跳过**（2026-11-11 自测
# 踩到），看起来像通过其实没测。按修改时间取最新的 dist/Desktop-sing-v*/。
_cands = sorted(
    (d for d in glob.glob(os.path.join(BASE, "dist", "Desktop-sing-v*"))
     if os.path.isfile(os.path.join(d, "Desktop-sing.exe"))),
    key=lambda d: os.path.getmtime(d), reverse=True)
exe = os.path.join(_cands[0], "Desktop-sing.exe") if _cands else ""
if _cands:
    print("    使用产物：%s" % os.path.basename(_cands[0]))
if os.path.isfile(exe):
    # ⚠️ 必须用**隔离的数据目录**跑：真机集成依赖「进程保活」设置，而用户
    # 可能在设置里关掉了它（本机 config.json 就是 keepalive=False），直接拿真实
    # CFG_DIR 跑会必然 FAIL，还会往用户配置目录写 keepalive.off 哨兵（2026-11-11
    # 自测踩到）。CFG_DIR 取自 %APPDATA%，给子进程换一个空 APPDATA 就是全新
    # 默认配置（keepalive 默认 True），测完删掉，零污染。
    _tmp_appdata = tempfile.mkdtemp(prefix="wdtest_appdata_")
    _tmp_cfg = os.path.join(_tmp_appdata, L.APP_NAME)
    _env = dict(os.environ)
    _env["APPDATA"] = _tmp_appdata
    _env.pop(L.SUPERVISED_ENV, None)
    app = subprocess.Popen([exe], creationflags=DETACHED,
                           cwd=os.path.dirname(exe), env=_env)
    try:
        time.sleep(9.0)
        pids = wd_pids()
        check("守护进程为主程序常驻", len(pids) >= 1, str(pids))
        if pids:
            mem = mem_private_kb(pids[0][0])
            ws_kb = pids[0][1]
            check("守护进程私有内存 < 8MB（Python 版 ~55MB）",
                  mem is not None and 0 < mem < 8192,
                  "私有 %s K ｜ 工作集 %s K" % (
                      ("%.0f" % mem) if mem is not None else "?", ws_kb))
        # 哨兵 + 结束主程序：守护进程不得重拉，应随主程序退出收工
        # （哨兵写在隔离目录里，别碰用户的 keepalive.off）
        _tmp_sentinel = os.path.join(_tmp_cfg, "keepalive.off")
        with open(_tmp_sentinel, "w") as f:
            f.write(str(int(time.time())))
        subprocess.run(["taskkill", "/F", "/IM", "Desktop-sing.exe"],
                       capture_output=True)
        check("停机流程：主程序退出后守护进程收工", wait_no_wd(12))
    finally:
        subprocess.run(["taskkill", "/F", "/IM", "Desktop-sing.exe"],
                       capture_output=True)
        shutil.rmtree(_tmp_appdata, ignore_errors=True)
else:
    print("  跳过：未找到 %s" % exe)

print("\n==== 结果: %s ===="
      % ("全部通过" if all(results) else "存在失败"))
sys.exit(0 if all(results) else 1)
