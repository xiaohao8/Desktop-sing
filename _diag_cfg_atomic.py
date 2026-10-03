# -*- coding: utf-8 -*-
"""诊断：save_config 是否原子（写入中途被杀会不会毁掉用户全部设置）。

原实现是 open(path, "w") 直接截断 + json.dump。配置不算大，但只要进程在
写一半时被终止（关机、任务管理器"结束任务"、崩溃、被杀软拦），磁盘上留下
的就是**半截 JSON**；下次启动 load_config() 的 except 会静默返回 {}，
用户所有设置（字号/配色/热键/位置/更新地址）一次性全丢，且**没有任何提示**。

本脚本用「写到一半就中断」模拟不可中断的进程死亡，看事后能不能读回配置。
"""
import io, json, os, sys, tempfile, shutil

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import lyrics_overlay as L

CFG = {
    "font_scale": 1.35, "color_theme": "aurora", "hotkeys": True,
    "opacity": 0.78, "pos_x": 1840, "pos_y": 320,
    "update_url": "https://example.com/update.json",
}


def simulate_interrupted_write(path, cfg, cut_at):
    """模拟：open('w') 截断后只写了 cut_at 字节就死了。"""
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text[:cut_at])
        f.flush()
        os.fsync(f.fileno())
    return text


def main():
    print("=" * 72)
    print("诊断：save_config 写入中途被中断 → 用户设置是否全丢")
    print("=" * 72)
    d = tempfile.mkdtemp(prefix="ds_cfg_")
    path = os.path.join(d, "config.json")
    full = json.dumps(CFG, ensure_ascii=False, indent=2)
    L.CONFIG_PATH = path
    try:
        # 1) 正常写：基线
        L.save_config(CFG)
        ok = L.load_config()
        print("[1] 正常写入 → 读回 %d 个键 %s" % (
            len(ok), "✓" if ok.get("font_scale") == 1.35 else "✗"))
        base_ok = ok.get("font_scale") == 1.35

        # 2) 各截断点：模拟进程在写入中途被 terminate
        print()
        print("  截断点      文件大小   能否解析   load_config 结果")
        print("  " + "-" * 60)
        lost_all = 0
        for frac, label in ((0.15, "15%"), (0.4, "40%"), (0.7, "70%"), (0.95, "95%")):
            cut = int(len(full) * frac)
            simulate_interrupted_write(path, CFG, cut)
            size = os.path.getsize(path)
            try:
                json.load(io.open(path, encoding="utf-8"))
                parsed = "可解析"
            except Exception:
                parsed = "❌ 损坏"
            got = L.load_config()
            empty = (got == {})
            if empty:
                lost_all += 1
            print("  %-10s %6d B   %-8s   %s" % (
                label, size, parsed,
                "{} ← 全部设置丢失" if empty else "%d 个键" % len(got)))
        print()
        if lost_all:
            print("→ ❌ %d/%d 个截断点都会导致**全部设置静默丢失**" % (
                lost_all, 4))
            print("   load_config 的 except 吞掉一切，用户看不出发生了什么，")
            print("   只觉得「软件怎么回到默认设置了」——没有任何提示可循。")
        else:
            print("→ ✓ 未复现设置丢失")
        return 0 if not lost_all else 1
    finally:
        L.CONFIG_PATH = os.path.join(os.environ.get("APPDATA", d), "Desktop-sing",
                                     "config.json")
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
