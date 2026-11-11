# -*- coding: utf-8 -*-
"""验证 is_info_line 修复：超长行零回溯 + 标题行判定行为不变"""
import re, time, sys

# ---- 复刻修复后的实现（与 lyrics_overlay.py 同步） ----
_CREDIT_PAT = re.compile(
    r"^\s*(歌词|词|曲|作曲|作词|编曲|混音|制作| 发行|出品)"
    r"|lyric|by\s*[::]|制作|歌词", re.I)  # 简化版，仅测标题行逻辑用不到它
_INFO_PAT = re.compile(r"(?!x)x")          # 永不匹配：专注测标题行逻辑
_TITLE_DASH = re.compile(r"\s+-\s+")
_SIDE_BAD = re.compile(r"\s\s|[，。！？、,.!?；;：:]")

def is_info_line(text):
    t = (text or "").strip()
    if not t:
        return False
    if _INFO_PAT.search(t):
        return True
    if re.search(r"[，。！？、,.!?；;：:]", t):
        return False
    parts = _TITLE_DASH.split(t)
    if len(parts) != 2:
        return False
    l, r = parts[0].strip(), parts[1].strip()
    if not l or not r:
        return False
    if _SIDE_BAD.search(l) or _SIDE_BAD.search(r):
        return False
    a, b = len(l), len(r)
    if max(a, b) < 3:
        return False
    if abs(a - b) > 12 or min(a, b) < max(a, b) / 3.0:
        return False
    return True

# ---- 旧实现（正则版），仅用于对照短行行为 ----
_SIDE = r"[^\s，。！？、,.!?；;：:](?:[^\s，。！？、,.!?；;：:]+[ ]?){0,22}[^\s，。！？、,.!?；;：:]"
_OLD_PAT = re.compile(r"^\s*(?P<l>" + _SIDE + r")\s+-\s+(?P<r>" + _SIDE + r")\s*$")
def old_is_info(text):
    t = (text or "").strip()
    if re.search(r"[，。！？、,.!?；;：:]", t):
        return False
    m = _OLD_PAT.match(t)
    if not m:
        return False
    a, b = len(m.group("l")), len(m.group("r"))
    if max(a, b) < 3:
        return False
    if abs(a - b) > 12 or min(a, b) < max(a, b) / 3.0:
        return False
    return True

fails = []
def chk(desc, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + desc + " -> " + str(got))
    if not ok:
        fails.append(desc)

# 1) ReDoS 触发行：必须毫秒级返回 False
long_no_punct = "abcdefghij " * 40          # 400 字符、词间单空格、无标点
long_words = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do " * 3).strip()
cases_redos = [
    ("400字无标点", long_no_punct),
    ("超长英文无标点", long_words),
    ("超长base64", "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" * 10),
    ("长URL行", "https://example.com/" + "a/b/c/d/e/f/g/h/i/j" * 30),
    ("空格+连字符诱导", "- " + "a b c d e f g h i j k l m n o p q r s t u v w x y z " * 8 + "- aaa"),
    ("仅空格和字母+结尾-", ("word " * 25) + "- x"),
]
print("== ReDoS 防护（必须全部 <0.05s） ==")
for desc, s in cases_redos:
    t0 = time.time()
    got = is_info_line(s)
    dt = time.time() - t0
    print("%s %.4fs -> %s" % (desc, dt, got))
    if dt > 0.05:
        fails.append("ReDoS " + desc)

# 2) 与旧实现行为对齐（同一行文本喂给新旧实现，结果必须一致）
align_cases = [
    "周杰伦 - 起风了",
    "周杰伦 - 最长的电影",
    "Anson Seabra - Welcome to Wonderland",
    "我想 - 你想",
    "爱 - 恨",
    "聚散 - 离合",
    "我想 - 你想，",
    "我 - 远远的太阳",
    "失落的岛屿 - 深海鱼子",
    "G弦上的咏叹调",
    "Bach - G弦上的咏叹调",
    "Taylor Swift - Love Story",
    "一二三四五六七八九十 - 一二三四五六七八九十",
    "loser - 来吧 亲爱的",
]
print("== 行为对齐（新旧实现对比） ==")
for t in align_cases:
    chk(t, is_info_line(t), old_is_info(t))
# 旧实现跑不动的行：只断言新实现返回 False（不误删）
for t in ["长长的侧边文字很多字 - 短词", "A - B - C"]:
    chk("(仅新实现) " + t, is_info_line(t), False)

# 3) 语义护栏：正常歌词不被误删
print("== 歌词护栏 ==")
chk("正常歌词行不受影响", is_info_line("沿着路上足迹"), False)
chk("带空格的歌词行", is_info_line("我 在 这 里 等 你"), False)

print()
if fails:
    print("FAILED:", fails); sys.exit(1)
print("ALL PASS")
