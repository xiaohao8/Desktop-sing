# -*- coding: utf-8 -*-
"""巡检脚本共用的「配置沙箱」：临时改写 config.json，退出时无条件还原。

为什么抽成独立模块
------------------
`smoke_test.py` / `_diag_saver_layout.py` / `_diag_saver_visual.py` / `preview_render.py`
都要先把用户配置换成一份「固定桩」（关掉全局快捷键、关掉保活、关掉空闲屏保），再构造
`LyricOverlay` —— 否则跑一次巡检就会去抢热键、拉守护进程、改用户设置。

早期各脚本自己写这段逻辑，踩了三个坑（都是真实发生过的）：

  ① **并行跑会互相删备份**。A 与 B 同时启动：两人都 `copy2(CFG, BAK)`（**同一个**路径），
     B 先结束 → 还原 + `os.remove(BAK)`；A 后结束再 `copy2(BAK, CFG)` 就拿到
     `FileNotFoundError`，脚本以退出码 1 收场（断言明明全过）。
  ② **备份可能备到的是「别人的临时桩」**。即使把备份路径按脚本名区分、崩溃问题没了，
     后启动的一方仍可能读到前一方刚写下的临时桩，还原时就把假配置留在用户配置上——
     不崩，但结果是错的（更危险）。
  ③ **异常退出根本走不到还原代码**。被 SIGTERM（跑太久超时）或中途报错时，还原代码
     在文件末尾压根执行不到，配置永久停在临时桩上。

本模块的应对
------------
  · **跨进程锁**（`config.json.sandbox.lock`）：同一时刻只允许一个沙箱生效。
    后来者会短暂等待，超时则抢占并打印告警 —— 把「并行」变成正确串行，
    既不会崩，也不会还原出错内容。残留锁（上次被 kill 留下的）按**持有进程是否还在**
    立即抢占 —— 只看 mtime 会让下一次运行白等整个 timeout（实测踩过：pid 早已消失，
    却因为锁文件「不够旧」而白等 90s）。pid 读不出来时才退回 mtime 判定。
  · 备份路径**按脚本名区分**（`config.json.prevbak.<脚本名>`），互不干扰。
  · 还原注册到 `atexit`，正常退出 / 抛异常 / `sys.exit()` 都会走到。
  · 额外接管 SIGTERM/SIGINT，被杀之前先把配置还回去、把锁放掉。
  · 还原失败只吞异常、绝不抛：诊断脚本的退出码应当只表示「断言过不过」。

用法
----
    import _cfg_sandbox
    _cfg_sandbox.begin(hotkeys=False, keepalive=False, idle_saver=False)
    ...                       # 此后 config.json 即为临时内容
    _cfg_sandbox.restore()    # 可选：想确定性还原时显式调用（atexit 是兜底）

也可以当上下文管理器：

    with _cfg_sandbox.sandbox(hotkeys=False):
        ...

环境变量
--------
`_CFG_SANDBOX_NO_LOCK=1` 跳过加锁（明知会冲突、只想快速跑一下时用）。
"""
import atexit
import json
import os
import shutil
import signal
import sys
import time

CFG = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                   "Desktop-sing", "config.json")
LOCK = CFG + ".sandbox.lock"
LEGACY_BAK = CFG + ".prevbak"       # 旧版共用的备份路径，顺手清掉
LOCK_WAIT = 90.0                    # 等锁上限（秒）；超时抢占
LOCK_STALE = 600.0                  # 锁超过这么久没更新 → 视为残留

_state = {"bak": None, "had": False, "done": True, "locked": False}


def bak_path():
    """当前脚本专属的备份路径（按脚本名区分，避免并行巡检互删）。"""
    raw = os.path.basename(sys.argv[0] or "")
    tag = "".join(c for c in os.path.splitext(raw)[0]
                  if c.isalnum() or c in "._-").strip("._-")
    if not tag or raw.startswith("-"):
        tag = "session"             # `python -c` / 交互式：拿不到脚本名
    return CFG + ".prevbak." + tag


def _pid_alive(pid):
    """锁的持有进程是否还活着。判断不了时保守返回 True（宁可等，不要抢）。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True                 # 自己持有：绝不抢自己的锁
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
            if not h:
                return False
            k.CloseHandle(h)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True


def _lock_owner():
    try:
        with open(LOCK, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def _acquire_lock(timeout=LOCK_WAIT):
    """拿锁；拿不到就等，超时（或锁已是残留）则抢占。返回是否拿到。

    残留判定优先看**持有进程是否还在**（进程被 kill 后锁文件会留下，但 pid 已消失），
    mtime 只在 pid 读不出来时兜底 —— 只看 mtime 会让上次崩溃留下的锁把下一次运行
    白等整个 timeout。
    """
    if os.environ.get("_CFG_SANDBOX_NO_LOCK"):
        return False
    deadline = time.time() + timeout
    note = 0
    while True:
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            owner = _lock_owner()
            try:
                age = time.time() - os.path.getmtime(LOCK)
            except OSError:
                age = 0.0
            if not _pid_alive(owner):
                print("[cfg] 锁的持有者（pid %s）已不存在，抢占残留锁" % (owner or "?"))
                _release_lock()
                continue
            if age > LOCK_STALE:
                print("[cfg] 锁文件已陈旧（%.0fs 无更新），抢占：%s" % (age, LOCK))
                _release_lock()
                continue
            if time.time() >= deadline:
                print("[cfg] !! 等锁超时，仍继续（另一个巡检可能正在跑，"
                      "配置还原可能不准）")
                return False
            left = int(deadline - time.time())
            if left != note and left >= 5 and left % 5 == 0:
                note = left
                print("[cfg] 另一个巡检正在跑（pid %s），等待配置锁 …（还剩 %ds）"
                      % (owner or "?", left))
            time.sleep(0.25)
            continue
        except OSError:
            return False
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True


def _release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def _restore():
    if _state["done"]:
        return
    _state["done"] = True
    bak = _state["bak"]
    try:
        if _state["had"] and bak and os.path.exists(bak):
            shutil.copy2(bak, CFG)
            os.remove(bak)
        elif not _state["had"]:
            os.remove(CFG)          # 原本就没有配置 → 删掉临时桩，别留假配置
    except OSError:
        pass
    if _state["locked"]:
        _release_lock()


def _on_signal(signum, frame):      # noqa: ARG001  被信号中断：先还配置再死
    _restore()
    os._exit(1)


def begin(**overrides):
    """加锁 → 备份用户配置 → 写入临时桩 → 注册退出还原。返回临时桩内容。"""
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    _state["locked"] = _acquire_lock()
    _state["bak"] = bak_path()
    _state["had"] = os.path.exists(CFG)
    _state["done"] = False
    if _state["had"]:
        try:
            shutil.copy2(CFG, _state["bak"])
        except OSError:
            _state["had"] = False   # 备份不了就当原本没有，宁可不还原也别覆盖
    if os.path.exists(LEGACY_BAK):  # 清掉旧版遗留的共享备份
        try:
            os.remove(LEGACY_BAK)
        except OSError:
            pass
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(overrides, f)
    atexit.register(_restore)
    for sig in ("SIGTERM", "SIGINT"):
        try:
            signal.signal(getattr(signal, sig), _on_signal)
        except (AttributeError, ValueError, OSError):
            pass
    return overrides


restore = _restore


class sandbox:                      # noqa: N801  小写：当上下文管理器用
    """`with _cfg_sandbox.sandbox(**overrides):` —— 出块自动还原。"""

    def __init__(self, **overrides):
        self.overrides = overrides

    def __enter__(self):
        begin(**self.overrides)
        return self

    def __exit__(self, *exc):
        _restore()
        return False


def reset():
    """把 config.json 复原成「全新安装」态（空配置 → 全部走默认值）。

    巡检崩溃导致临时桩遗留在用户配置上时，用它收拾残局：
    `python -c "import _cfg_sandbox; _cfg_sandbox.reset()"`
    """
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump({}, f)
