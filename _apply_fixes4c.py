# -*- coding: utf-8 -*-
"""v2.0.1 第四轮修复（第三处）：配置写入原子化 + 损坏文件自动救援。

问题（_diag_cfg_atomic.py 实测 4/4 复现）：
    save_config 用 open(path, "w") **直接截断**原文件再 json.dump。
    进程在写一半被终止（关机 / 任务管理器结束任务 / 崩溃 /被杀软拦），
    磁盘上留下半截 JSON；下次启动 load_config() 的 except 静默返回 {}，
    用户全部设置（字号/配色/热键/位置/更新地址）一次性丢失，**且无任何提示**。

修法（业界标准做法）：
    1. 先写同目录临时文件 → flush + os.fsync 落盘 → os.replace 原子替换。
       os.replace 在 Windows 与 POSIX 上都是原子的（同一卷内），
       因此配置**要么是旧的完整内容，要么是新的完整内容**，没有中间态。
    2. load_config 遇到损坏时，把坏文件另存为 config.json.corrupt，
       并尝试从它恢复出**能解析的键**（常见损坏形态是尾部被截断，
       前面的键往往还是完整合法的）。恢复成功就在日志里留痕，
       用户下次启动不至于"莫名其妙回到默认"却查不到原因。
CRLF 安全 + 幂等。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")

OLD = '''def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
'''

NEW = '''def _salvage_json(text: str) -> dict:
    """从半截 JSON 里尽力救回完整的键值对。

    典型损坏形态是**尾部被截断**（写一半被杀），前面的键往往完整合法。
    逐个扫描 `"key":` 片段，用 json.JSONDecoder().raw_decode 解析紧随其后的值，
    解析成功就收下；到坏掉的地方自然停下。比直接返回 {} 强得多。
    """
    out = {}
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while True:
        j = text.find('":', i)
        if j < 0:
            break
        k0 = text.rfind('"', max(0, j - 200), j + 1)
        if k0 < 0:
            i = j + 2
            continue
        key = text[k0 + 1:j]
        if not key:
            i = j + 2
            continue
        try:
            val, end = dec.raw_decode(text[j + 2:].lstrip())
        except ValueError:
            i = j + 2                       # 这个值坏了，往后找下一个键
            continue
        lead = len(text[j + 2:]) - len(text[j + 2:].lstrip())
        i = j + 2 + lead + end
        try:
            out[key] = val
        except Exception:
            pass
        if i >= n:
            break
    return out


def load_config():
    """读配置。损坏不静默吞掉：留一份 .corrupt 并尽力抢救可读的键。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as ex:
        # 走到这里说明文件存在但解析失败（多半是上次写入中途被杀）。
        # 保留现场供排查，并尝试抢救 —— 至少别让用户白丢设置。
        salvaged = {}
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                raw = f.read()
            try:
                with open(CONFIG_PATH + ".corrupt", "w", encoding="utf-8") as cf:
                    cf.write(raw)
            except OSError:
                pass
            salvaged = _salvage_json(raw)
        except Exception:
            pass
        if salvaged:
            log("config corrupted (%s), salvaged %d keys from %s"
                % (ex, len(salvaged), CONFIG_PATH))
        else:
            log("config corrupted (%s) and nothing salvageable: %s"
                % (ex, CONFIG_PATH))
        return salvaged


def save_config(cfg: dict):
    """原子写：临时文件落盘后 os.replace 覆盖，避免半截配置毁掉用户设置。

    os.replace 在同卷内是原子操作（Windows 上走 MoveFileEx 替换语义），
    因此配置文件只会是「旧的完整内容」或「新的完整内容」，没有中间态。
    """
    tmp = "%s.tmp" % CONFIG_PATH
    try:
        d = os.path.dirname(CONFIG_PATH)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())      # 真正落盘，别只留在系统缓冲里
        os.replace(tmp, CONFIG_PATH)  # 原子替换
    except OSError:
        # 替换失败就把临时文件清掉，别留垃圾（.corrupt 保留给用户看）
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    old, new = OLD.replace("\n", nl), NEW.replace("\n", nl)
    if new in src:
        print("skip：配置原子化已应用")
        return 0
    if src.count(old) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(old))
        return 1
    src = src.replace(old, new, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("ok：配置写入原子化 + 损坏救援")
    return 0


if __name__ == "__main__":
    sys.exit(main())
