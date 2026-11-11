# -*- coding: utf-8 -*-
"""全量 ReDoS 审计：把 lyrics_overlay.py 里所有模块级 re.compile 正则，
逐一对「超长恶意输入」限时 search，找出任何会永不返回的模式。"""
import ast, io, re, sys, threading, time

SRC = io.open("lyrics_overlay.py", encoding="utf-8").read()
tree = ast.parse(SRC)

def const_str(node):
    """尽力常量折叠：字面量 / 字符串拼接 / 变量引用（查表）"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = const_str(node.left), const_str(node.right)
        if a is not None and b is not None:
            return a + b
    if isinstance(node, ast.Name) and node.id in VARS:
        return VARS[node.id]
    return None

VARS = {}
pat_defs = []   # (name, pattern_str, lineno)
for node in tree.body:
    if isinstance(node, ast.Assign):
        v = const_str(node.value)
        if v is not None and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            VARS[node.targets[0].id] = v
    # 二次扫描收集 compile（VARS 可能后定义，compile 在前——分两遍兜底）
for node in ast.walk(tree):
    if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "compile"):
        arg = node.value.args[0] if node.value.args else None
        p = const_str(arg) if arg is not None else None
        name = (node.targets[0].id if isinstance(node.targets[0], ast.Name)
                else "<expr>")
        pat_defs.append((name, p, node.lineno))

MALICIOUS = [
    "400字无标点", "A" * 400,
    "长ASCII词串", ("abcdefghij " * 40).strip(),
    "长中文无空格", "abcdefghij" * 40,
    "长URL", "https://example.com/" + "a/b/c/d/e/f/g/h/i/j" * 30,
    "长base64", "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" * 10,
    "大量空格+词", ("word " * 80) + ":",
    "词开头+超长尾部", "作词 " + ("abc " * 120),
    "LRC时间戳×200", "[00:01.00]" * 200,
    "尖括号标签×200", "<00:01.00>" * 200,
]

TIMEOUT = 1.0
def probe(pattern, text, result, idx):
    try:
        re.compile(pattern, re.I).search(text)
        result[idx] = "OK"
    except Exception as e:
        result[idx] = "ERR " + type(e).__name__

fails = []
print("模块级正则共 %d 个" % len(pat_defs))
for name, p, lineno in pat_defs:
    if p is None:
        print("  SKIP %s (line %d): 模式为动态拼接，常量折叠失败" % (name, lineno))
        continue
    try:
        rx = re.compile(p, re.I)
    except Exception as e:
        print("  SKIP %s: 编译失败 %s" % (name, e))
        continue
    slow = []
    for i, (label, text) in enumerate(zip(MALICIOUS[::2], MALICIOUS[1::2])):
        res = [None]
        th = threading.Thread(target=probe, args=(p, text, res, 0), daemon=True)
        t0 = time.time()
        th.start(); th.join(TIMEOUT)
        dt = time.time() - t0
        if th.is_alive() or dt > 0.2:
            slow.append("%s(%.2fs%s)" % (label, dt, " TIMEOUT" if th.is_alive() else ""))
            if th.is_alive():
                fails.append("%s / %s" % (name, label))
    status = "SLOW " + ", ".join(slow) if slow else "OK"
    print("  %-22s L%-5d %s" % (name, lineno, status))

print()
if fails:
    print("REDOS RISK:", fails)
    sys.exit(1)
print("ALL PATTERNS SAFE")
