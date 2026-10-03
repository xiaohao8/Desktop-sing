# -*- coding: utf-8 -*-
"""给冒烟测试加第四轮第三组：config_atomic_write。

覆盖：
  1. save_config 走 os.replace 原子替换（不留 .tmp）
  2. 写入中途被中断的残留半截配置，load_config 能**抢救**可读的键，
     而不是静默返回 {} 让用户全部设置凭空消失
  3. 损坏现场留 .corrupt 供排查
幂等 + CRLF 安全。
"""
import io, os, sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke_test.py")
MARK = 'check("config atomic write", config_atomic_write)'

ANCHOR = 'check("async fetch ordering", async_fetch_ordering)'

BLOCK = '''

def config_atomic_write():
    """配置写入必须原子；半截配置要能抢救，不能静默全丢"""
    import json as _json
    import shutil as _sh
    import tempfile as _tf
    fails = []

    def ck(cond, why):
        if not cond:
            fails.append(why)

    real = L.CONFIG_PATH
    d = _tf.mkdtemp(prefix="ds_cfg_")
    p = os.path.join(d, "config.json")
    L.CONFIG_PATH = p
    try:
        cfg = {"font_scale": 1.35, "color_theme": "aurora", "hotkeys": True,
               "opacity": 0.78, "pos_x": 1840, "pos_y": 320,
               "update_url": "https://example.com/update.json"}
        L.save_config(cfg)
        got = L.load_config()
        ck(got.get("font_scale") == 1.35, "正常写入读不回: %r" % (got,))
        ck(got.get("color_theme") == "aurora", "正常写入丢键: %r" % (got,))
        # 原子替换不该留临时文件
        ck(not os.path.exists(p + ".tmp"),
           "os.replace 没清掉临时文件: " + str(os.listdir(d)))
        names = os.listdir(d)
        ck(names == ["config.json"], "目录里有意料之外的残留: %r" % (names,))

        # --- 半截配置：模拟写入中途进程被杀留下的现场
        text = _json.dumps(cfg, ensure_ascii=False, indent=2)
        for frac, min_keys in ((0.40, 2), (0.70, 5), (0.95, 5)):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text[:int(len(text) * frac)])
            salv = L.load_config()
            ck(len(salv) >= min_keys,
               "截断 %d%% 只救回 %d 个键（应 >=%d）：%r"
               % (int(frac * 100), len(salv), min_keys, salv))
            ck(isinstance(salv, dict), "截断 %d%% 返回的不是 dict" % int(frac * 100))
        # 抢救出的键必须类型正确（不能把数字读成字符串这类）
        ck(isinstance(salv.get("font_scale"), float),
           "font_scale 类型被读错: %r" % (type(salv.get("font_scale")),))
        ck(salv.get("hotkeys") is True, "hotkeys 布尔值读错: %r" % (salv.get("hotkeys"),))
        # 损坏现场要留档
        ck(os.path.exists(p + ".corrupt"), "损坏配置没留 .corrupt 供排查")

        # --- 键名引号被截断的极端形态（旧实现的假引号坑）
        with open(p, "w", encoding="utf-8") as f:
            f.write(text[:int(len(text) * 0.15)])
        s15 = L.load_config()
        ck(isinstance(s15, dict), "键名中途截断返回的不是 dict: %r" % (s15,))

        # --- 文件不存在时返回空 dict（不是 rescue 路径）
        os.remove(p)
        for extra in (".corrupt", ".tmp"):
            q = p + extra
            if os.path.exists(q):
                os.remove(q)
        ck(L.load_config() == {}, "无配置文件时不该返回非空")

    finally:
        L.CONFIG_PATH = real
        _sh.rmtree(d, ignore_errors=True)
    for w in fails:
        check("config atomic write",
              lambda w=w: (_ for _ in ()).throw(AssertionError(w)))
    return True


check("config atomic write", config_atomic_write)
'''


def main():
    with io.open(SRC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if MARK in src:
        print("skip：第三组已存在")
        return 0
    nl = "\r\n" if "\r\n" in src else "\n"
    anchor = ANCHOR.replace("\n", nl)
    block = BLOCK.replace("\n", nl)
    if src.count(anchor) != 1:
        print("FAIL：锚点出现 %d 次" % src.count(anchor))
        return 1
    src = src.replace(anchor, anchor + block, 1)
    with io.open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("written: %s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
