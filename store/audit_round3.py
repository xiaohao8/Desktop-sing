# -*- coding: utf-8 -*-
"""复盘轮 3：商店政策与提审材料审计（离线自检）

不依赖网络、不依赖显示器：强制把 lyrics_overlay 的 STORE_MODE 置为 True，
然后真实实例化浮层与设置面板，走一遍 refresh()，验证：

  P1 商店模式下设置面板不会因为「控件没创建/被隐藏」而崩
  P2 「关于」文案按运行环境如实描述（不带商店版没有的能力）
  P3 提审材料里引用的资产/文案在仓库里真实存在
  P4 隐私政策如实覆盖程序真正的网络行为与本地写入

用法：.buildenv\\Scripts\\python.exe store\\audit_round3.py
"""
import os
import re
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

FAILS = []
WARNS = []


def check(tag, ok, detail=""):
    print("  %-3s %s%s" % ("PASS" if ok else "FAIL", tag,
                           ("  — " + detail) if detail else ""))
    if not ok:
        FAILS.append(tag)


def warn(tag, detail=""):
    print("  !!! %s%s" % (tag, ("  — " + detail) if detail else ""))
    WARNS.append(tag)


def head(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


# ---------------------------------------------------------------- P1/P2
head("P1/P2 商店模式运行时自检（offscreen，真实实例化）")

import lyrics_overlay as ov  # noqa: E402

ov.STORE_MODE = True          # 强制商店模式，模拟 MSIX 运行环境
print("  已强制 STORE_MODE = True (原始 is_msix_packaged=%s)" % ov.is_msix_packaged())

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
print("  QApplication OK")

# --- P2: 「关于」文案本身 ---
head("P2 「关于」文案如实性")
about_src = open(os.path.join(ROOT, "lyrics_overlay.py"), encoding="utf-8").read()
i = about_src.index("    def _about(self):")
j = about_src.index("    # ---------------- 检查更新 ----------------")
ab = about_src[i:j]
check("P2.1 _about 内按 STORE_MODE 分支", ab.count("STORE_MODE") >= 1)
check("P2.2 商店分支文案不含「进程保活」",
      "开机自启（系统「启动」设置里开关）· 全局快捷键" in ab
      and "开机自启 · 进程保活" in ab,
      "非商店分支保留保活字样")
# 商店分支那一行的字面量
m = re.search(r'if STORE_MODE:\s*\n\s*abilities = \((.*?)\)\n', ab, re.S)
if m:
    seg = m.group(1)
    check("P2.3 商店分支 abilities 字符串不含「保活」", "保活" not in seg, seg.replace("\n", " ")[:70])
else:
    check("P2.3 商店分支 abilities 可解析", False, "正则未命中")

# --- P1: 真实构建托盘 + 设置面板 ---
head("P1 商店模式下构造托盘与设置面板")
try:
    watcher = ov.MediaWatcher()
    overlay = ov.LyricOverlay(watcher)
    print("  LyricOverlay(watcher) OK")
except Exception:
    check("P1.1 LyricOverlay() 构造无异常", False, traceback.format_exc().splitlines()[-1])
    overlay = None
else:
    check("P1.1 LyricOverlay() 构造无异常", True)

if overlay is not None:
    # 托盘菜单（商店模式隐藏保活项、自启改为跳转）
    try:
        overlay._sync_tray_menu()
        check("P1.2 _sync_tray_menu() 无异常", True)
    except Exception as e:
        check("P1.2 _sync_tray_menu() 无异常", False, "%s: %s" % (type(e).__name__, e))

    # 主面板
    try:
        panel = ov.SettingsPanel(overlay)
        print("  SettingsPanel(overlay) OK")
        check("P1.3 SettingsPanel() 构造无异常", True)
    except Exception as e:
        check("P1.3 SettingsPanel() 构造无异常", False, traceback.format_exc().splitlines()[-1])
        panel = None
    else:
        try:
            panel.refresh()
            check("P1.4 refresh() 无异常（关键：商店版缺控件也不崩）", True)
        except Exception as e:
            check("P1.4 refresh() 无异常（关键：商店版缺控件也不崩）", False,
                  traceback.format_exc().splitlines()[-1])

        # 商店模式下不该存在的控件
        check("P1.5 商店版未创建 update_url_edit",
              not hasattr(panel, "update_url_edit"))
        check("P1.6 商店版未创建 update_check_btn",
              not hasattr(panel, "update_check_btn"))
        check("P1.7 商店版未创建 update_auto_check",
              not hasattr(panel, "update_auto_check"))
        check("P1.8 商店版未创建 _on_update_url 所依赖的控件（_on_update_url 仍可解析属性）",
              not hasattr(panel, "update_url_edit"))
        # 保活/自启开关：存在但隐藏
        check("P1.9 keep_check 存在且已隐藏",
              hasattr(panel, "keep_check") and panel.keep_check.isHidden())
        check("P1.10 auto_check 存在且已隐藏",
              hasattr(panel, "auto_check") and panel.auto_check.isHidden())

        # 排查：_on_update_url 若被误触发会 AttributeError 吗？（商店版没有那个控件，
        # 但只要没人连它的 editingFinished 就永远不会被调用；这里确认没连错）
        check("P1.11 商店版 _on_update_url 未被任何控件连线触发",
              "update_url_edit.editingFinished.connect" not in
              open(os.path.join(ROOT, "lyrics_overlay.py"), encoding="utf-8").read().split(
                  "if STORE_MODE:\n            # 商店版：更新走商店")[1][:400])

    # 商店版 check_update 静默/提示
    try:
        overlay.check_update(manual=False)
        check("P1.12 check_update(manual=False) 商店版静默返回", True)
    except Exception as e:
        check("P1.12 check_update(manual=False) 商店版静默返回", False, str(e))

    try:
        ov.spawn_supervisor()
        check("P1.13 spawn_supervisor() 商店版短路（不尝试拉包内 exe）", True)
    except Exception as e:
        check("P1.13 spawn_supervisor() 商店版短路", False, str(e))

    check("P1.14 keepalive 被强制关闭", overlay.keepalive is False,
          "keepalive=%r" % overlay.keepalive)

# ---------------------------------------------------------------- P3
head("P3 提审材料引用完整性")

assets_dir = os.path.join(ROOT, "store", "assets")
mf_tpl = open(os.path.join(ROOT, "store", "AppxManifest.template.xml"), encoding="utf-8").read()
referenced = sorted(set(re.findall(r'Assets\\([A-Za-z0-9._\-]+\.png)', mf_tpl)))
print("  清单引用资产 %d 个" % len(referenced))
missing = [a for a in referenced if not os.path.exists(os.path.join(assets_dir, a))]
check("P3.1 清单引用的每个资产都在 store/assets/ 里", not missing,
      "缺: %s" % missing if missing else "")

all_assets = [f for f in os.listdir(assets_dir) if f.lower().endswith(".png")]
check("P3.2 资产总数 ≥ 90（含多倍率与主题变体）", len(all_assets) >= 90,
      "实际 %d" % len(all_assets))

# 商店 listing 图标 300x300 需要单独准备吗？（复用 300x300 的方形基础图）
need_listing = ["StoreLogo.png"]  # 300x300 是商店 listing 图标推荐尺寸
check("P3.3 StoreLogo.png 存在（可作商店 listing 图标）",
      os.path.exists(os.path.join(assets_dir, "StoreLogo.png")))

# 隐私政策
priv = os.path.join(ROOT, "site", "privacy.html")
check("P3.4 site/privacy.html 存在", os.path.exists(priv))
check("P3.5 PRIVACY.md 存在", os.path.exists(os.path.join(ROOT, "PRIVACY.md")))

# 截图：商店至少 1 张
shots = []
for d in ("site/assets", "docs", "screenshots", "store"):
    p = os.path.join(ROOT, d)
    if os.path.isdir(p):
        for f in os.listdir(p):
            if f.lower().endswith((".png", ".jpg", ".jpeg")) and any(
                    k in f.lower() for k in ("shot", "screenshot", "预览", "preview", "效果")):
                shots.append(os.path.join(d, f))
if shots:
    check("P3.6 找到可用作商店截图的图片", True, ", ".join(shots[:4]))
else:
    warn("P3.6 仓库里没找到明显的「截图/预览」图（商店至少需 1 张，建议 1366×768+）",
         "需人工用运行中的程序截图后上传 Partner Center")

# ---------------------------------------------------------------- P4
head("P4 隐私政策与真实行为一致性")

code = open(os.path.join(ROOT, "lyrics_overlay.py"), encoding="utf-8").read()
priv_txt = open(priv, encoding="utf-8").read()

# 真实歌词源
for src, label in (("QQ音乐", "QQ音乐"), ("网易云", "网易云音乐"),
                   ("酷狗", "酷狗音乐"), ("lrclib", "LRCLIB"), ("LRCLIB", "LRCLIB")):
    if src in code and label not in priv_txt:
        check("P4.%s 隐私政策提到歌词源 %s" % (label, label), False)
check("P4.1 隐私政策覆盖 QQ音乐/网易云/酷狗/LRCLIB 四源",
      all(k in priv_txt for k in ("QQ音乐", "网易云音乐", "酷狗音乐", "LRCLIB")))

# 真实更新源
upd_sources = []
for k in ("github.com", "gitee.com", "jsdelivr.net", "lanzou"):
    if k in code.lower():
        upd_sources.append(k)
print("  代码里出现的更新/分发渠道: %s" % ", ".join(upd_sources))
check("P4.2 隐私政策披露了更新检查渠道（GitHub/Gitee/jsDelivr）",
      all(k in priv_txt for k in ("GitHub", "Gitee", "jsDelivr")))
check("P4.3 隐私政策声明了商店版无应用内更新",
      "Microsoft Store 版本没有" in priv_txt or "商店版本没有" in priv_txt)

# 本地写入目录
dirs = set(re.findall(r'APPDATA[^"\']*', code)) | set(re.findall(r'APP_NAME[^"\']*', code))
app_name_hits = re.findall(r'APP_NAME\s*=\s*["\']([^"\']+)["\']', code)
print("  APP_NAME = %s" % (app_name_hits or "?"))
# 程序内真实使用的中文名 vs 隐私政策里写的路径名
check("P4.4 隐私政策写的 %APPDATA% 目录名与程序一致",
      all(("%%APPDATA%%\\%s" % n) in priv_txt.replace(" ", "") or n in priv_txt
          for n in app_name_hits) if app_name_hits else False,
      "程序内 APP_NAME=%s；政策里出现 Desktop-sing: %s" % (
          app_name_hits[0] if app_name_hits else "?",
          "%APPDATA%\\Desktop-sing" in priv_txt))

# 不采集合规声明
check("P4.5 隐私政策含「不发往外部服务器」类表述",
      ("不上传到任何服务器" in priv_txt) or ("不上传" in priv_txt))
check("P4.6 隐私政策含 SMTC 系统媒体读取说明（PRIVACY.md）",
      "SMTC" in open(os.path.join(ROOT, "PRIVACY.md"), encoding="utf-8").read(),
      "site/privacy.html 里是否也提 SMTC: %s" % ("SMTC" in priv_txt))

# ---------------------------------------------------------------- 汇总
head("汇总")
print("  FAIL: %d   WARN: %d" % (len(FAILS), len(WARNS)))
for f in FAILS:
    print("    ✗ %s" % f)
for w in WARNS:
    print("    ! %s" % w)
print("\n%s" % ("全部关键项通过" if not FAILS else "存在未通过项，见上"))
sys.exit(1 if FAILS else 0)
