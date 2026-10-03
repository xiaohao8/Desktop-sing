# -*- coding: utf-8 -*-
"""修 _salvage_json：上一版两个 bug 导致 0 救援成功。

  bug1: rfind('"', max(0, j-200), j+1) 的右界 j+1 落在**结束引号本身**，
        于是 rfind 找到的就是它 → key 恒为 ''，直接 continue 掉全部键。
  bug2: 截断点落在**键名引号内部**时，find('":') 会先匹配到键名开头的
        假引号（15% 截断就是这种），后面全是噪声。

改法：走行解析。save_config 用 indent=2，每个键必然独占一行
      `    "key": value,` —— 按行找 `"..." :` 的**行内完整引号对**，
      再用 raw_decode 解析行内值；解析不出来的行跳过，继续扫后面的行。
CRLF 安全 + 幂等（锚点是函数整体）。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lyrics_overlay.py")

OLD = '''    out = {}
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
'''

NEW = '''    out = {}
    dec = json.JSONDecoder()
    # save_config 固定 indent=2，每个键必然独占一行；按行走最省心。
    # 不能用 find('":') 在整篇里裸搜：截断点落在键名引号内部时会先匹配到
    # 键名开头的假引号（实测 15% 截断就属于这种），后面全是噪声。
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        # 必须是**行内成对的**引号：键名完整才谈得上解析
        if len(line) < 4 or not line.startswith('"'):
            continue
        q = line.find('"', 1)
        if q <= 0:
            continue
        key = line[1:q]
        rest = line[q + 1:].lstrip()
        if not rest.startswith(":"):
            continue
        rest = rest[1:].strip()
        if not rest:
            continue
        try:
            val, _end = dec.raw_decode(rest)
        except ValueError:
            continue          # 这个值被截断了，跳过；后面的行还能救
        out[key] = val
    return out
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    old, new = OLD.replace("\n", nl), NEW.replace("\n", nl)
    if new in src:
        print("skip：salvage 已修")
        return 0
    if src.count(old) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(old))
        return 1
    src = src.replace(old, new, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("ok：_salvage_json 改为按行解析")
    return 0


if __name__ == "__main__":
    sys.exit(main())
