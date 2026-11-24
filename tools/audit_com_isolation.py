# -*- coding: utf-8 -*-
"""COM/WinRT 隔离静态审计 —— 2026-11-13 商店版挂死事故的防回归门禁。

事故回顾（v2.0.3）：`CoInitializeEx(APARTMENTTHREADED)` 被做在 SMTC 采集线程上，
MSIX 沙箱里采集线程随后在 `try_get_media_properties_async` 上永久挂死，
20s 心跳日志消失，歌词彻底不获取（v2.0.4 修复：COM 全部隔离到专属
audio-probe 线程 + 所有 WinRT await 一律 `asyncio.wait_for` 超时）。

本脚本对 lyrics_overlay.py 强制两条铁律（基于 ast 语法树，字符串字面量
里的 CSS 花括号等干扰一概免疫），构建前必跑，违例即退出码 1：

  铁律一  COM API（CoInitializeEx / CoInitialize / CoUninitialize /
          CoCreateInstance / CoTaskMemFree / PropVariantClear）只允许出现在
          「明确隔离的探针类」体内：class _AudioProbe / class _QQMusicProbe。
          两者各自在自己的后台线程里 CoInitializeEx，采集线程与 UI 线程都不碰
          COM；新增探针类必须同时加进 ALLOWED_PROBE_CLASSES，不允许静默放行。
  铁律二  任何对 WinRT 异步方法（调用名以 _async 结尾，如 request_async /
          try_get_media_properties_async / open_read_async / load_async）的
          await，必须直接包在 `asyncio.wait_for(..., <超时>)` 里——卡死只准
          损失一次轮询，绝不允许无超时等待。

用法：python tools/audit_com_isolation.py [源文件路径]
"""
import ast
import os
import sys

DEFAULT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "lyrics_overlay.py")

COM_ATTRS = {"CoInitializeEx", "CoInitialize", "CoUninitialize",
             "CoCreateInstance", "CoTaskMemFree", "PropVariantClear"}

# 允许持有 COM 单线程公寓的类（每个都必须自己起独立线程，见各自类注释）
ALLOWED_PROBE_CLASSES = ("_AudioProbe", "_QQMusicProbe")


def _attr_name(node):
    """Attribute 链的最末端名字；非 Attribute 返回 None"""
    node = node.func if isinstance(node, ast.Call) else node
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_wait_for(call):
    """call 是否为 asyncio.wait_for / wait_for(...)"""
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr == "wait_for"
    if isinstance(f, ast.Name):
        return f.id == "wait_for"
    return False


def audit(path):
    try:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return False, ["源码语法错误，无法审计: 第 %d 行 %s" % (e.lineno, e.msg)]
    errors = []

    # 类体行号范围（1 基，含装饰器/类头到类体结束）
    def class_range(name):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == name:
                return node.lineno, node.end_lineno
        return None

    probe_ranges = {}
    for name in ALLOWED_PROBE_CLASSES:
        rng = class_range(name)
        if rng is None:
            return False, ["找不到 class %s：文件结构变了，审计规则需要同步更新"
                           % name]
        probe_ranges[name] = rng
    watcher_rng = class_range("MediaWatcher")

    # 遍历所有 Await 与 Call 节点，并建立父链以便判定「包没包 wait_for」
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr.endswith("_async")):
            continue
        # 找到包裹它的 await（若有）
        n = node
        await_node = None
        while n in parents:
            n = parents[n]
            if isinstance(n, ast.Await):
                await_node = n
                break
            if isinstance(n, ast.Call) and _is_wait_for(n):
                continue            # wait_for 的参数层，继续向上找 await
        if await_node is None:
            continue                # 非 await 的 _async 调用（如传引用），不适用铁律二
        # await 的对象是否就是 wait_for(...) 调用（wait_for 是 await 的子节点）
        wrapped = isinstance(await_node.value, ast.Call) and _is_wait_for(await_node.value)
        if not wrapped:
            errors.append("第 %d 行: WinRT 异步调用 %r 未包 asyncio.wait_for（铁律二）"
                          % (node.lineno, node.func.attr))

    # 铁律一：COM 调用只许在明确隔离的探针类体内
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _attr_name(node) in COM_ATTRS:
            ln = node.lineno
            owner = next((n for n, (a, b) in probe_ranges.items()
                          if a <= ln <= b), None)
            if owner is None:
                errors.append("第 %d 行: COM 调用 %r 出现在隔离探针类之外（铁律一）"
                              % (ln, _attr_name(node)))
            if watcher_rng and watcher_rng[0] <= ln <= watcher_rng[1]:
                errors.append("第 %d 行: MediaWatcher 采集线程内出现 COM 调用 %r"
                              % (ln, _attr_name(node)))

    return (not errors), errors


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    ok, errors = audit(path)
    if ok:
        print("AUDIT PASS: COM 隔离两条铁律全部合规 (%s)" % os.path.basename(path))
        return 0
    print("AUDIT FAIL (%d 处违例):" % len(errors))
    for e in errors:
        print("  - " + e)
    return 1


if __name__ == "__main__":
    sys.exit(main())
