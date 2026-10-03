# -*- coding: utf-8 -*-
"""给 config_atomic_write 补两条判别力更强的断言（补 M7/M9 漏网）。

M7 漏网原因：原断言只验「正常写完不留 .tmp」，而直接截断写在**顺利**完成时
也照样不留 .tmp —— 区分不开。真正能区分的是**写一半失败**：
序列化中途抛错时，直接截断版已经把原文件destroy成半截 JSON；
原子版（临时文件 + os.replace）原文件**完好无损**。
（实测 json.dump 遇到不可序列化对象会在已写出一半时抛 TypeError。）

M9 是等价变异体（那行 startswith 判断本就多余，删掉不影响行为）——
不写变异体，改为把冗余判断清掉，让代码与断言一一对应。
幂等 + CRLF 安全。
"""
import io, os, sys

SRC_T = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.py")
MARK = "# --- 写一半失败时原配置必须完好（M7 判别锚点）"
SRC_L = SRC_T.replace("smoke_test.py", "lyrics_overlay.py")

# ---- 1) 清掉 _salvage_json 里的冗余 startswith 判断（M9 等价变异体的根因）
OLD_L = '''        line = line.strip().rstrip(",")
        # 必须是**行内成对的**引号：键名完整才谈得上解析
        if len(line) < 4 or not line.startswith('"'):
            continue
        q = line.find('"', 1)
        if q <= 0:
            continue
'''
NEW_L = '''        line = line.strip().rstrip(",")
        # 必须是**行内成对的**引号：键名完整才谈得上解析
        if len(line) < 4:
            continue
        q = line.find('"', 1)
        if q <= 0:
            continue
'''

# ---- 2) 给冒烟补「写一半失败」断言
OLD_T = '''        # --- 文件不存在时返回空 dict（不是 rescue 路径）'''

NEW_T = '''        # --- 写一半失败时原配置必须完好（M7 判别锚点）
        #     json.dump 遇到不可序列化对象会在已写出一半时抛 TypeError。
        #     原子写：异常发生在临时文件上，CONFIG_PATH 一字未动。
        #     直接截断写：原文件已被 destroy 成半截 JSON，配置全丢。
        good = {"font_scale": 1.35, "color_theme": "aurora", "hotkeys": True}
        L.save_config(good)
        baseline = L.load_config()
        ck(baseline.get("font_scale") == 1.35, "前置写入失败: %r" % (baseline,))
        broken = {"a": 1, "b": 2, "bad": object(), "c": 4}
        try:
            L.save_config(broken)
        except Exception:
            pass                      # save_config 内部已兜住，这里只是防御
        after = L.load_config()
        ck(after.get("font_scale") == 1.35,
           "写一半失败把原配置毁了：%r" % (after,))
        ck(after.get("color_theme") == "aurora",
           "写一半失败丢了 color_theme：%r" % (after,))
        # 半截残留若存在（原文件路径），也不该是损坏的主配置
        raw = ""
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                raw = f.read()
        try:
            json.loads(raw) if raw else None
            intact = True
        except Exception:
            intact = False
        ck(intact or after.get("font_scale") == 1.35,
           "主配置损坏且无法抢救：%r" % (raw[:80],))

        # --- 文件不存在时返回空 dict（不是 rescue 路径）'''


def patch(path, old, new, label):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    o, n = old.replace("\n", nl), new.replace("\n", nl)
    if n in src:
        print("skip  %s" % label)
        return 0
    if src.count(o) != 1:
        print("FAIL  %s：锚点出现 %d 次" % (label, src.count(o)))
        return 1
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(src.replace(o, n, 1))
    print("ok    %s" % label)
    return 0


def main():
    with io.open(SRC_T, "r", encoding="utf-8", newline="") as f:
        t = f.read()
    if MARK in t:
        print("skip：M7 判别锚点已在")
        return 0
    rc = patch(SRC_T, OLD_T, NEW_T, "补「写一半失败」断言")
    if rc:
        return rc
    rc = patch(SRC_L, OLD_L, NEW_L, "清掉 _salvage_json 冗余判断")
    return rc


if __name__ == "__main__":
    sys.exit(main())
