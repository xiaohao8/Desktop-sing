# -*- coding: utf-8 -*-
"""诊断：候选匹配是否会「拿到不匹配的歌词还自认优质」。

怀疑点：_match_candidates 只对搜索结果**排序**后取前 3，从不**否决**明显不匹配的
候选；score_lyrics 又只看「有无逐字/有无翻译/行数」，不看内容对不对。
两者叠加 → 同名歌 / 翻唱 / 合辑误命中时，一份「逐字齐全但歌词是别的歌」的结果
反而会拿最高分被采纳。

本脚本直接打真实接口，验证：
  A. 歌名完全匹配的候选能否稳定排到第 1（正常路径不能被破坏）；
  B. 歌手明显不符的候选会不会被放进前三（错配路径）。
"""
import sys
import time

sys.path.insert(0, r"C:\Users\35436\Desktop\代码\desktop-lyrics")

import lyrics_overlay as L


def probe(query, title, artist, label):
    print("=" * 68)
    print(f"[{label}]  query={query!r}  title={title!r}  artist={artist!r}")
    for src, fn in (("qq", L.fetch_qq_search),
                    ("netease", L.fetch_netease_search),
                    ("kugou", L.fetch_kugou_search)):
        t0 = time.time()
        try:
            cands = fn(query, timeout=6.0)
        except Exception as e:
            print(f"  {src:<8} 异常: {type(e).__name__}: {e}")
            continue
        dt = (time.time() - t0) * 1000
        picked = L._match_candidates(cands, title, artist)
        norm_t, norm_a = L.norm_text(title), L.norm_text(artist)
        print(f"  {src:<8} 返回 {len(cands or [])} 条，{dt:.0f}ms，取前 "
              f"{len(picked)} 条：")
        for i, it in enumerate(picked):
            nm = it.get("name") or ""
            sg = it.get("singer") or it.get("singers") or ""
            if isinstance(sg, (list, tuple)):
                sg = "/".join(str(x) for x in sg)
            name_ok = L.norm_text(nm) == norm_t
            singer_ok = bool(norm_a) and norm_a in L.norm_text(str(sg))
            flag = "OK " if (name_ok and singer_ok) else ("歌名✓歌手✗" if name_ok else "都不符")
            print(f"      {i+1}. [{flag}] {nm}  —  {sg}")
    print()


if __name__ == "__main__":
    L.ensure_idna_codec()
    # A. 正常路径：热门中文歌
    probe("起风了", "起风了", "买辣椒也用券", "正常-精确歌名歌手")
    probe("海阔天空", "海阔天空", "Beyond", "正常-乐队名")
    # B. 风险路径：歌名很常见，同名歌多
    probe("晴天", "晴天", "周杰伦", "风险-同名歌极多")
    probe("无所谓", "无所谓", "杨千嬅", "风险-同名歌多")
    # C. 翻唱场景
    probe("童话", "童话", "光良", "风险-同名歌多(翻唱)")
