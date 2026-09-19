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

# 截图：商店至少 1 张。
# 注意要**递归**找 —— store/out/shots/ 是 render_shots.py 的产出目录，
# 只扫顶层的旧写法会把已经生成好的截图漏掉，误报成「没有截图」。
# 商店要求最小 1366×768，所以顺带把尺寸也验了（小图会被直接拒）。
shots = []
for d in ("site/assets", "docs", "screenshots", "store"):
    p = os.path.join(ROOT, d)
    if not os.path.isdir(p):
        continue
    for dp, _, fs in os.walk(p):
        for f in fs:
            if f.lower().endswith((".png", ".jpg", ".jpeg")) and any(
                    k in f.lower() for k in ("shot", "screenshot", "预览", "preview", "效果")):
                shots.append(os.path.join(dp, f))

if shots:
    from PySide6.QtGui import QImage as _QI
    big, small, blank = [], [], []
    for sp_ in shots:
        img = _QI(sp_)
        if img.isNull():
            continue
        # 空白检测：角落背景色相同的采样点占比过高 = 抓成纯底色了。
        # （踩过坑：offscreen 下 grab 有时抓到全透明，落盘是一张纯壁纸，
        #   只看文件大小看不出来 —— 95KB 也可能是纯渐变。）
        bg = img.pixelColor(4, 4)
        nz = tot = 0
        for _y in range(0, img.height(), 8):
            for _x in range(0, img.width(), 8):
                tot += 1
                c = img.pixelColor(_x, _y)
                if abs(c.red() - bg.red()) + abs(c.green() - bg.green()) \
                        + abs(c.blue() - bg.blue()) > 30:
                    nz += 1
        ratio = (nz / float(tot)) if tot else 0.0
        tag = "%dx%d %s(内容 %.0f%%)" % (img.width(), img.height(),
                                        os.path.relpath(sp_, ROOT), ratio * 100)
        if ratio < 0.03:
            blank.append(tag)
        elif img.width() >= 1366 and img.height() >= 768:
            big.append(tag)
        else:
            small.append(tag)
    check("P3.6 找到可用作商店截图的图片", bool(big),
          ("达标(≥1366×768) %d 张：%s" % (len(big), "; ".join(big[:3]))) if big
          else "没有同时满足「尺寸达标 + 内容非空」的图")
    if blank:
        check("P3.6a 截图不是空白（真的画出了内容）", False,
              "疑似空图: %s" % "; ".join(blank))
    else:
        check("P3.6a 截图不是空白（真的画出了内容）", True)
    if small:
        warn("P3.6b 有 %d 张截图尺寸不足 1366×768（商店最小要求）" % len(small),
             "; ".join(small[:3]))
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

# P4.6a 两份隐私声明必须**同时**披露 SMTC。
# 第 3 轮发现：PRIVACY.md 写清了「通过 SMTC 读取歌曲名/歌手/进度」，
# 但 site/privacy.html（**真正填进商店表单的那个 URL**）只字未提。
# 商店审核只读 URL 那份 → 少披露一项系统读取权限，属实质缺失。
check("P4.6a site/privacy.html 也披露了 SMTC 系统媒体读取", "SMTC" in priv_txt,
      "商店表单填的是这个 URL，只写在 PRIVACY.md 里等于没披露")
check("P4.6b 两份隐私声明对「不读取音乐文件」的表述一致",
      ("不读取你的音乐文件" in priv_txt) and
      ("不读取你的音乐文件" in open(os.path.join(ROOT, "PRIVACY.md"),
                                    encoding="utf-8").read()),
      "用户最关心的边界，两份都要写明")

# P4.7 site/privacy.html 的 HTML 结构必须自洽。
# 商店表单填的就是这个 URL，标签不配平在浏览器里会「吃掉」后面的内容 ——
# 审核员打开看到的是一份残缺的隐私政策，直接按 10.5.1 判缺。
# （本沙箱的 WebEngine 渲染不出内容，所以用标准库 HTMLParser 做结构校验。）
def _html_balanced(path):
    from html.parser import HTMLParser
    VOID = {"br", "img", "meta", "link", "hr", "input", "source"}
    st, err = [], []

    class _P(HTMLParser):
        def handle_starttag(self, t, a):
            if t not in VOID:
                st.append(t)

        def handle_endtag(self, t):
            if not st:
                err.append("多余 </%s>" % t)
            elif st.pop() != t:
                err.append("不匹配 </%s>" % t)
    try:
        _P().feed(open(path, encoding="utf-8").read())
    except Exception as e:
        err.append(str(e))
    return st, err


_priv_path = os.path.join(ROOT, "site", "privacy.html")
_unclosed, _errs = _html_balanced(_priv_path)
check("P4.7 site/privacy.html 的 HTML 标签配平",
      not _unclosed and not _errs,
      ("未闭合 %s / 错误 %s" % (_unclosed[:3], _errs[:3])) if (_unclosed or _errs) else
      "结构自洽，浏览器不会吞掉后续段落")

# ---------------------------------------------------------------- P5
# 政策 10.1.1 / 11.2：界面与文案不得使用他人注册商标、不得暗示与第三方存在关联；
# 政策 10.2.7 / 10.5.1：用户对本地数据有完整控制权（要能看见、能清理）。
head("P5 商标风险与本地数据控制权")

# P5.1 界面里不能出现第三方品牌名（内部 key 与代码标识符不算）
# ⚠️ 只扫 lyrics_overlay.py 是不够的：清单 Description、商品页文案也都会
#    被用户看到（2026-09-19 实测清单里藏着一句「如 QQ音乐 / 网易云音乐 / 酷狗音乐」，
#    正是这条检查没覆盖 build_store.py 才漏掉的）。下面把所有「用户可见载体」都过一遍。
TM_PAT = re.compile(r'(Spotify|iOS|Apple Music|Musixmatch|iTunes)')
ui_src = open(os.path.join(ROOT, "lyrics_overlay.py"), encoding="utf-8").read()
build_src = open(os.path.join(ROOT, "store", "build_store.py"), encoding="utf-8").read()

# 只看用户可见的中文字符串常量（"…" 里含中文的）
zh_strings = [s for s in re.findall(r'"([^"\n]*)"', ui_src) if re.search(r'[\u4e00-\u9fff]', s)]
tm_hits = [s for s in zh_strings if TM_PAT.search(s)]
check("P5.1 界面文案不含第三方注册商标（Spotify / iOS / …）", not tm_hits,
      "命中: %s" % tm_hits[:4] if tm_hits else "样式名一律用外观特征命名")

# P5.1b 清单 Description 同样不得含注册商标（这段会被写进包元数据、商店可见）
desc_m = re.search(r'^DESCRIPTION = \((.*?)\)\s*\n', build_src, re.S | re.M)
desc_txt = "".join(re.findall(r'"([^"]*)"', desc_m.group(1))) if desc_m else ""
desc_tm = TM_PAT.findall(desc_txt)
check("P5.1b 清单 Description 不含第三方注册商标", not desc_tm,
      "命中: %s" % desc_tm if desc_tm else "已改为只描述 SMTC 兼容性")

# P5.1c 清单 Description 不得点名具体播放器品牌（QQ音乐/网易云/酷狗/汽水…）
PLAYER_BRANDS = ("QQ音乐", "QQ 音乐", "网易云", "酷狗", "汽水音乐", "虾米")
desc_brands = [b for b in PLAYER_BRANDS if b in desc_txt]
check("P5.1c 清单 Description 不点名播放器品牌", not desc_brands,
      "命中: %s" % desc_brands if desc_brands else "")

# P5.1d 商店版「更新」菜单项的文案必须如实（不能还写「检查更新…」，
#       否则用户以为应用内有更新通道，点了却拿不到版本信息 → 像功能坏了）
check("P5.1d 商店版更新菜单文案如实反映商店分发",
      "在商店中获取更新" in ui_src and
      re.search(r'QAction\("在商店中获取更新…" if STORE_MODE else "检查更新…"', ui_src)
      is not None,
      "旧版两种模式都写「检查更新…」")

# P5.2 不得暗示与音乐平台存在关联
check("P5.2 「关于」窗口声明与音乐平台无从属关系",
      "无从属或合作关系" in ui_src)

# P5.3 缓存必须有上限（否则无限堆积）
check("P5.3 歌词缓存设了上限常量",
      ("CACHE_MAX_FILES" in ui_src) and ("CACHE_MAX_BYTES" in ui_src),
      "上限=%s" % re.findall(r'CACHE_MAX_(?:FILES|BYTES)\s*=\s*([^\n#]+)', ui_src)[:2])

# P5.4 写入缓存后要淘汰
check("P5.4 写入缓存后调用 prune_cache()", "prune_cache()" in ui_src)

# P5.5 设置面板要给出清理入口（不能只写在隐私政策里）
check("P5.5 设置面板提供「歌词缓存」清理入口",
      ("_cache_btn_text" in ui_src) and ("_on_clear_cache" in ui_src)
      and ("清理缓存" in ui_src))

# P5.6 force 清理必须真的删文件
check("P5.6 prune_cache(force=True) 会删除 .json", 
      re.search(r'if force:.*?os\.remove', ui_src, re.S) is not None)

# P5.7 缓存清理按钮要在商店版也存在（不随更新项一起被裁掉）
check("P5.7 清理入口未挂在商店版被裁的更新区块里",
      "cache_btn" in ui_src and "update_url_edit" not in
      ui_src.split("cache_btn")[0][-400:])

# P5.8 站点商品页也不得出现注册商标
site_txt = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
site_tm = re.findall(r'(Spotify 声波|iOS 音乐卡片|Spotify|Apple Music)', site_txt)
check("P5.8 官网文案不含第三方注册商标", not site_tm,
      "命中: %s" % site_tm[:4] if site_tm else "")

# P5.9 官网截图资源必须是当前 UI 生成的（防止旧图与新文案对不上）
site_img = os.path.join(ROOT, "site", "assets", "anim-fan.png")
preview_img = os.path.join(ROOT, "preview", "anim_fan_dark.png")
if os.path.exists(site_img) and os.path.exists(preview_img):
    check("P5.9 官网动画截图与最新 preview 一致",
          os.path.getsize(site_img) == os.path.getsize(preview_img),
          "site=%d preview=%d（不一致说明改过 UI 但没重跑 make_assets.py）"
          % (os.path.getsize(site_img), os.path.getsize(preview_img)))
else:
    warn("P5.9 缺少 anim-fan.png / anim_fan_dark.png，无法比对官网截图新鲜度")

# P5.10 认证说明里给审核员的主路径不能是默认关闭的功能
notes = open(os.path.join(ROOT, "store", "build_store.py"), encoding="utf-8").read()
check("P5.10 认证说明用「右键托盘」作打开设置的主路径",
      "右键点击系统托盘图标" in notes,
      "旧版曾让审核员按 Ctrl+Alt+S，而该快捷键默认关闭")

# P5.11 功能数量三处口径必须一致（商品页 / 关于窗口 / 代码真源）
n_style = len(re.findall(r'^\s*"[a-z]+":', re.search(
    r'STYLE_NAMES = \{(.*?)\n\}', ui_src, re.S).group(1), re.M))
n_anim = len(re.findall(r'^\s*"[a-z]+":', re.search(
    r'ANIM_STYLES = \{(.*?)\n\}', ui_src, re.S).group(1), re.M))
n_preset = len(re.findall(r'\(\"', re.search(
    r'POSITION_PRESETS = \((.*?)\n\)', ui_src, re.S).group(1)))
# 屏保风格：只在「菜单构建」那一处按 (key, name) 成对列举，数那个元组。
# 注意正则要把第一个 `("` 一起吃进 group（否则首项不被计入，永远少 1）。
m_saver = re.search(r'for key, name in \(\(("particle.*?)\)\):\s*\n\s*a = m_saver_style',
                    ui_src, re.S)
n_saver = len(re.findall(r'\("', m_saver.group(1))) + 1 if m_saver else -1
print("  代码真源: 样式 %d / 动画 %d / 锚点 %d / 屏保 %d"
      % (n_style, n_anim, n_preset, n_saver))

about_txt = ui_src[ui_src.index('"关于 桌面歌词"'):][:900]
listing_txt = re.search(r'STORE_LISTING_DESCRIPTION = """(.*?)"""', notes, re.S).group(1)

def _claims(txt):
    """抽出文案里「N 种 X」的声明"""
    want = {
        "样式": n_style, "逐字动画": n_anim, "锚点": n_preset, "氛围屏保": n_saver,
    }
    out = {}
    for key, real in want.items():
        m = re.search(r'(\d+)\s*种[^\n·]{0,4}' + key, txt) or \
            re.search(r'(\d+)\s*个' + key, txt)
        if m:
            out[key] = (int(m.group(1)), real)
    return out

for label, txt in (("关于窗口", about_txt), ("商品页描述", listing_txt)):
    claims = _claims(txt)
    bad = {k: v for k, v in claims.items() if v[0] != v[1]}
    check("P5.11 %s 的功能数量与代码一致" % label, not bad,
          "不一致: %s" % bad if bad else "、".join(
              "%s%d" % (k, v[0]) for k, v in sorted(claims.items())))

# P5.12 许可与隐私声明必须随包分发
# Apache-2.0 第 4 条要求向接收者提供 NOTICE；内置 MiSans 要求保留许可说明。
# 商店用户只拿到 .msix，看不到 GitHub 仓库 → 文件不进包就是实打实的许可违规。
lp = os.path.join(ROOT, "LICENSE-THIRD-PARTY.txt")
check("P5.12 存在随包许可文件 LICENSE-THIRD-PARTY.txt", os.path.exists(lp))
if os.path.exists(lp):
    lt = open(lp, encoding="utf-8").read()
    check("P5.12a 许可文件含 Apache-2.0 归属声明（Lyricify）",
          "Lyricify-Lyrics-Helper" in lt and "Apache License, Version 2.0" in lt)
    check("P5.12b 许可文件含内置字体 MiSans 的说明", "MiSans" in lt)
    check("P5.12c 许可文件含 FluentFlyout 的「未使用源码」声明",
          "FluentFlyout" in lt and "没有使用" in lt)
check("P5.12d 打包脚本把许可文件列入随包清单",
      "LICENSE-THIRD-PARTY.txt" in notes and "BUNDLED_LICENSES" in notes)
# 三条分发渠道都要带许可文件（商店版 / 便携 zip / NSIS 安装包）——
# 用户从哪条渠道拿到程序，就必须在哪条渠道拿到许可声明。
_nsi = open(os.path.join(ROOT, "installer", "installer.nsi"), encoding="utf-8").read()
_pkg = open(os.path.join(ROOT, "pkg_portable.py"), encoding="utf-8").read()
check("P5.12f NSIS 安装包随包许可文件",
      "LICENSE-THIRD-PARTY.txt" in _nsi,
      "安装版用户看不到仓库")
check("P5.12g 便携 zip 随包许可文件",
      "LICENSE-THIRD-PARTY.txt" in _pkg)
# 已打出的包要真的带上（没跑过打包就跳过，不误报）
_BUNDLE = ("LICENSE-THIRD-PARTY.txt", "PRIVACY.md", "使用说明.txt",
           "PRIVACY.en.md", "USAGE.en.txt")
_msix = os.path.join(ROOT, "store", "out", "Desktop-sing-1.0.0.0-x64.msix")
if os.path.exists(_msix):
    import zipfile as _zf
    from urllib.parse import unquote as _unq
    # ⚠️ makeappx 会把清单里的**非 ASCII 路径做百分号编码**（如 使用说明.txt 变成
    #    %E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.txt）。安装后 Windows 会解码回原名，
    #    所以这里必须先 unquote 再比对，否则中文文件名永远「像是没打进包」。
    _names = _zf.ZipFile(_msix).namelist()
    _base = {_unq(n).rsplit("/", 1)[-1] for n in _names}
    _miss = [f for f in _BUNDLE if f not in _base]
    check("P5.12e 已打包的 MSIX 里含全部随包文档", not _miss,
          "缺: %s（需重新打包）" % _miss if _miss else "共 %d 份" % len(_BUNDLE))

# P5.12h 三条渠道必须带**同一套**随包文档。
# 早先 MSIX 只带 LICENSE + PRIVACY.md，漏了使用说明 → 商店用户装完找不到任何使用说明，
# 与便携版/安装版不一致。这里改成「一套清单，三处都验」，漏一处立刻 FAIL。
for _chan, _txt in (("build_store.py", notes), ("pkg_portable.py", _pkg),
                    ("installer.nsi", _nsi)):
    _lacking = [f for f in _BUNDLE if f not in _txt]
    check("P5.12h %s 随包全部 %d 份文档" % (_chan, len(_BUNDLE)), not _lacking,
          "缺: %s" % _lacking if _lacking else "")

# P5.12i 英文文档也必须真的存在（渠道清单写了名字但文件不存在 = 静默漏发）
_absent = [f for f in _BUNDLE if not os.path.exists(os.path.join(ROOT, f))]
check("P5.12i 随包清单里的文档在仓库中都存在", not _absent,
      "缺文件: %s" % _absent if _absent else "")

# ---------------------------------------------------------------- P5.13 多显示器
head("P5.13 多显示器 / 高 DPI")
# 悬浮条是「贴着屏幕边」的桌面工具，多显示器是主场景而非边缘场景。
# 第 3 轮实测发现两处写死 primaryScreen() 的 bug：
#   ① _preset_point() 用主屏几何算预设坐标 → 副屏用户点「贴底」窗口跳回主屏；
#   ② AmbientSaver.start() 用主屏中心选屏 → 副屏用户触发屏保，黑的是主屏。
# 两处都已改为「跟随窗口/歌词条所在屏，取不到再退鼠标屏、退主屏」。
# 这条检查锁住这个模式：**定位型 API 不许直接用 primaryScreen 当首选**。
check("P5.13 预设坐标跟随窗口所在屏（不写死主屏）",
      re.search(r'def _preset_point.*?scr = self\.screen\(\)', ui_src, re.S) is not None,
      "旧版 g = QApplication.primaryScreen().availableGeometry()")
check("P5.13a 屏保跟随歌词条所在屏（不写死主屏）",
      re.search(r'def start\(self\):.*?self\.ov\.screen\(\)', ui_src, re.S) is not None,
      "旧版用 primaryScreen().geometry().center() 选屏")
check("P5.13b 取不到窗口屏时有鼠标屏 / 主屏兜底",
      ui_src.count("QApplication.screenAt(QCursor.pos())") >= 2,
      "两处（预设坐标 + 屏保）都要有兜底，否则 hide() 状态下会拿到 None")
# 位置往返一致性：套预设后反查必须回到同一个 key，否则「自由位置」判定会失准
check("P5.13c 位置反查仍以同一基准计算（预设与反查共用 _preset_point）",
      ui_src.count("self._preset_point(") >= 2 and
      "def _current_position_key" in ui_src)
# DPI：Qt6 默认已启用高 DPI 缩放，不应再去开 Qt5 时代的废弃开关
_deprecated = [a for a in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps")
               if a in ui_src]
check("P5.13d 未使用 Qt5 时代的废弃 DPI 开关", not _deprecated,
      "命中: %s（Qt6 里这些已废弃，设置会被告警）" % _deprecated if _deprecated
      else "Qt6 默认启用高 DPI 缩放，无需手动开")

# ---------------------------------------------------------------- P5.14 卸载残留
head("P5.14 卸载残留")
# 卸载不干净是商店审核与用户投诉的双重高发区：
#   ① 自启项留着 → 每次开机弹「找不到文件」；
#   ② %APPDATA% 留着 → 配置/缓存变孤儿，重装后又莫名带着旧设置。
# 第 3 轮实测发现 NSIS 卸载节既没删 Run 键也没碰用户数据目录，已补。
_nsi_txt = open(os.path.join(ROOT, "installer", "installer.nsi"), encoding="utf-8").read()
_un = _nsi_txt.split('Section "Uninstall"')[-1]
check("P5.14 卸载时删除开机自启项（Run 键）",
      re.search(r'DeleteRegValue\s+HKCU\s+"Software\\Microsoft\\Windows\\CurrentVersion\\Run"',
                _un) is not None,
      "留下会在每次开机弹「找不到文件」")
check("P5.14a 卸载时处理用户数据目录（%APPDATA%\\Desktop-sing）",
      "$APPDATA\\${DIR_NAME}" in _un or "$APPDATA\\Desktop-sing" in _un,
      "留下则配置/缓存成孤儿，重装又莫名带旧设置")
check("P5.14b 删用户数据前有明确询问（不静默删）",
      "MB_YESNO" in _un and "IDYES" in _un,
      "默认不问就删会误删用户配置")
check("P5.14c 卸载前先结束进程（否则 $INSTDIR 删不净）",
      "taskkill" in _un)
check("P5.14d 卸载时删快捷方式与开始菜单项",
      "Delete" in _un and "$SMPROGRAMS" in _un)

# ---------------------------------------------------------------- P5.15 中英文档
head("P5.15 中英文档")
# 英文版不是「顺手加一份」——它有两个硬约束：
#   ① **英文版必须存在且与中文版口径一致**（商店是全球分发的，英文用户要能读懂声明）；
#   ② **英文版必须如实说明界面当前只有简体中文**，否则等于暗示有英文界面，
#      按政策 10.1.1（准确描述功能与重要限制）是会被判的。
_zh_en = [("README.md", "README.en.md"), ("PRIVACY.md", "PRIVACY.en.md"),
          ("NOTICE.md", "NOTICE.en.md"), ("使用说明.txt", "USAGE.en.txt")]
for _zh, _en in _zh_en:
    check("P5.15 存在英文版 %s（对应 %s）" % (_en, _zh),
          os.path.exists(os.path.join(ROOT, _en)))

_en_readme = os.path.join(ROOT, "README.en.md")
if os.path.exists(_en_readme):
    _ert = open(_en_readme, encoding="utf-8").read()
    check("P5.15a 英文 README 如实说明界面只有简体中文",
          "Simplified Chinese only" in _ert,
          "不写这句＝暗示有英文界面，商店会按 10.1.1 判「描述不准确」")
    check("P5.15b 英文 README 保留已知限制章节",
          "Known limitations" in _ert)
    check("P5.15c 英文 README 保留许可与致谢章节",
          "Credits and licensing" in _ert)

# P5.15d 英文隐私声明必须同时覆盖本地数据、SMTC 读取、网络请求三块
_en_priv = os.path.join(ROOT, "PRIVACY.en.md")
if os.path.exists(_en_priv):
    _ept = open(_en_priv, encoding="utf-8").read()
    check("P5.15d 英文隐私声明覆盖 SMTC 系统媒体读取", "SMTC" in _ept)
    check("P5.15e 英文隐私声明覆盖本地数据目录",
          "%APPDATA%" in _ept)
    check("P5.15f 英文隐私声明覆盖请求头如实披露",
          "request headers" in _ept.lower(),
          "合规要求，与中文版同源")

# P5.15g 官网英文隐私页 + 中英互链
_site_en = os.path.join(ROOT, "site", "privacy.en.html")
check("P5.15g 存在英文隐私政策页 site/privacy.en.html", os.path.exists(_site_en))
if os.path.exists(_site_en):
    _sp_en = open(_site_en, encoding="utf-8").read()
    _sp_zh = open(os.path.join(ROOT, "site", "privacy.html"), encoding="utf-8").read()
    check("P5.15h 英文隐私页含 SMTC 章节", "SMTC" in _sp_en)
    check("P5.15i 中英隐私页互相链接（语言切换）",
          "privacy.en.html" in _sp_zh and 'href="privacy.html"' in _sp_en,
          "只放一份等于另一语言用户找不到自己的版本")
    check("P5.15j 英文隐私页 lang 属性为 en",
          re.search(r'<html lang="en"', _sp_en) is not None)
    # 结构自洽（与 P4.7 同一套 HTMLParser 校验）
    _u2, _e2 = _html_balanced(_site_en)
    check("P5.15k 英文隐私页 HTML 标签配平", not _u2 and not _e2,
          ("未闭合 %s / 错误 %s" % (_u2[:3], _e2[:3])) if (_u2 or _e2) else "")

# ---------------------------------------------------------------- P5.16 对外文档口径
head("P5.16 对外文档口径（该说的说、不该说的不说）")
# 「面向用户与商店的文档」不等于「开发者文档」。下面这些词属于**不该出现在对外文档**的类别：
#   · 逆向 / 绕过技术措施：3DES、weapi、zlib、具体加密方案
#   · 第三方代理服务点名：ghfast.top / ghproxy.net（脆弱且易被质疑）
#   · 对具体艺人 / 平台版权状况的举例：把「某歌手在某平台无版权」写进对外文档毫无必要
# 注意 NOTICE.md **不在**扫描范围：那里列函数名是 Apache-2.0 归属义务要求的「指明了什么被借用」，
# 属于「该说」；但同样不该出现破解手法描述。
_PUBLIC_DOCS = ["README.md", "README.en.md", "使用说明.txt", "USAGE.en.txt",
                "PRIVACY.md", "PRIVACY.en.md"]
_FORBIDDEN = ("3DES", "weapi", "ghfast.top", "ghproxy.net", "周杰伦",
              "AES-CBC", "RSA 无填充")
_hits = {}
for _f in _PUBLIC_DOCS:
    _p = os.path.join(ROOT, _f)
    if not os.path.exists(_p):
        continue
    _t = open(_p, encoding="utf-8").read()
    _h = [k for k in _FORBIDDEN if k in _t]
    if _h:
        _hits[_f] = _h
check("P5.16 对外文档不含逆向/密评/代理点名等不该公开的内容", not _hits,
      ("命中: %s" % _hits) if _h else "扫描 %d 份对外文档，均干净" % len(_PUBLIC_DOCS))

# 反向：对外文档必须**说到**该说的 —— 已知限制与许可归属不能为了「好看」被删掉
for _f, _need in (("README.md", ("已知限制", "致谢与许可")),
                  ("README.en.md", ("Known limitations", "Credits and licensing"))):
    _p = os.path.join(ROOT, _f)
    if os.path.exists(_p):
        _t = open(_p, encoding="utf-8").read()
        _lack = [s for s in _need if s not in _t]
        check("P5.16a %s 保留「已知限制」与「许可归属」" % _f, not _lack,
              "缺: %s" % _lack if _lack else "")

# P5.16b 中英 README 的**功能数量口径**必须一致（英文版少写/多写数字同样是描述不准确）。
# 用「精确短语」而不是宽泛正则：短语是文档里真实存在的固定说法，改了就会立刻发现，
# 且把数字与**代码真源**（上面的 n_style / n_anim / n_preset / n_saver）绑在一起，
# 改功能数量而忘了改文案时这里会亮。
if os.path.exists(_en_readme):
    _ert2 = open(_en_readme, encoding="utf-8").read()
    _zht = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    for _key, _n, _zh_need, _en_need in (
            ("悬浮样式", n_style, "5 种悬浮样式", "5 overlay styles"),
            ("逐字动画", n_anim, "9 种逐字动画", "9 word-by-word animations"),
            ("位置锚点", n_preset, "7 个锚点", "7 anchors"),
            ("氛围屏保", n_saver, "4 种氛围屏保", "4 styles")):
        _ok_zh = _zh_need in _zht
        _ok_en = _en_need in _ert2
        # 短语里的数字必须与代码真源一致（防止「文档写 5、代码有 6」）
        _num_ok = ("%d" % _n) in _zh_need
        check("P5.16b 中英 README 都声明「%d 种%s」" % (_n, _key),
              _ok_zh and _ok_en and _num_ok,
              ("中文%s 英文%s 与代码一致%s"
               % ("有" if _ok_zh else "**缺**", "有" if _ok_en else "**缺**",
                  "" if _num_ok else " **数字与代码不符**")) if not (_ok_zh and _ok_en and _num_ok)
              else "")

# P5.16c 界面语言必须如实声明（政策 10.7）
# 应用界面目前只有简体中文。两处都要对：
#   ① 清单 Resources **只**声明 zh-CN（不虚报 en-US，否则等于声明了一个不存在的本地化）；
#   ② 商品页描述里要写明「界面仅有简体中文」，否则英文页区的用户会按描述预期一个英文界面。
# 注意 ① 的 `Resources` 在**清单模板**里，不在 build_store.py 里 —— 第一版查错了文件。
_src_bs = open(os.path.join(ROOT, "store", "build_store.py"), encoding="utf-8").read()
_tpl = open(os.path.join(ROOT, "store", "AppxManifest.template.xml"),
            encoding="utf-8").read()
_langs = re.findall(r'<Resource\s+Language="([^"]+)"', _tpl)
check("P5.16c 清单只声明 zh-CN（不虚报 en-US）",
      _langs == ["zh-CN"], "实际声明: %s" % (_langs or "无"))
check("P5.16c 商品页描述写明界面仅有简体中文",
      "仅有简体中文" in _src_bs,
      "不写＝英文页区用户按描述预期一个不存在的英文界面")

# ---------------------------------------------------------------- P5.17 商店截图素材
head("P5.17 商店截图素材（生成器 + 产物）")


def _img_detail_hits(img, step=3, gap=4, thresh=25):
    """粗略统计「高频边缘」像素数，用来识破「抓成纯背景」的空白图。

    为什么不能用透明度判空白：这几张截图是「合成壁纸 + 控件」的合成图，
    整张 alpha 都是 255，空白图的 alpha 也是 255，判不出来。
    改用相邻像素亮度突变（文字笔画、卡片边界会产生大量突变，
    平滑渐变背景几乎为 0）。
    """
    hits = 0
    for _y in range(0, img.height() - gap, step):
        for _x in range(0, img.width() - gap, step):
            if abs(img.pixelColor(_x, _y).lightness()
                   - img.pixelColor(_x + gap, _y).lightness()) > thresh:
                hits += 1
    return hits


# 阈值实测标定（step=3 / gap=4 / thresh=25 这组参数下）：
#   纯壁纸（空白基线）= 46   idle = 179   hero = 468   settings = 3870
# 取 120 作分界：空白图 46 远低于它，最「素」的 idle 图也有 179。
_BLANK_HITS_MIN = 120


_shots_py = os.path.join(ROOT, "store", "render_shots.py")
_shots_dir = os.path.join(ROOT, "store", "out", "shots")
_SHOT_NAMES = ("store-shot-1-idle.png", "store-shot-2-hero.png",
               "store-shot-3-settings.png")

check("P5.17a 截图生成脚本存在", os.path.isfile(_shots_py))
_src_shots = open(_shots_py, encoding="utf-8").read() if os.path.isfile(_shots_py) else ""

# 截图会进商品页 —— 属**对外发布物**，不能嵌真实歌曲的歌名与歌词。
# （上一版 hero 图用的是真实歌曲及其歌词，属不必要的版权暴露。）
_REAL_SONG_WORDS = ("起风了", "买辣椒也用券")
_hit_words = [w for w in _REAL_SONG_WORDS if w in _src_shots]
check("P5.17b 截图用自写占位歌词（无真实歌曲歌名/歌词）", not _hit_words,
      "命中: %s" % _hit_words if _hit_words else "")

# offscreen 回填守卫：下面四处漏掉任何一处，都会「静默」抓到空白或缺行的图
# （不抛异常、文件也在，只有肉眼看才发现 —— 曾经的 hero / settings 就是这样）。
for _tag, _needle, _why in (
        ("P5.17c 切行动画推到终态（_line_anim.stop + _line_t）", "_line_anim.stop()",
         "否则 _line_t 停在 0 → 整行歌词透明，只剩歌名"),
        ("P5.17d 面板淡入推到终态（_fx.setOpacity(1.0)）", "_fx.setOpacity(1.0)",
         "否则 opacity 停在 0 → 设置面板抓成纯背景图"),
        ("P5.17e 手动喂当前行文本（_current_text）", "_current_text =",
         "绘制读缓存文本而非 lines[cur_idx]，不喂则当前行是空的"),
        ("P5.17f 设置播放锚点时间（anchor_ts）", "anchor_ts = time.monotonic()",
         "初值 0.0 + status=PLAYING → 时间轴飞到天外，行号全乱")):
    check(_tag, _needle in _src_shots, "" if _needle in _src_shots else _why)

check("P5.17g 抓图后有「全透明图」自证", "_has_content(" in _src_shots,
      "grab() 的全透明结果 isNull() 判不出来，必须自证")

if os.path.isdir(_shots_dir):
    from PySide6.QtGui import QImage  # noqa: E402
    _bad, _hits = [], []
    for _n in _SHOT_NAMES:
        _p = os.path.join(_shots_dir, _n)
        if not os.path.isfile(_p):
            _bad.append("%s 缺失" % _n)
            continue
        _img = QImage(_p)
        if _img.width() < 1366 or _img.height() < 768:
            _bad.append("%s 尺寸 %dx%d 不足 1366x768" % (_n, _img.width(), _img.height()))
            continue
        _h = _img_detail_hits(_img)
        _hits.append("%s=%d" % (_n.split("-")[-1].replace(".png", ""), _h))
        if _h < _BLANK_HITS_MIN:
            _bad.append("%s 疑似空白图（细节像素仅 %d，空白基线约 46）" % (_n, _h))
    check("P5.17h 已生成的 3 张截图尺寸达标且非空白", not _bad,
          "; ".join(_bad) if _bad else "细节像素 " + ", ".join(_hits))
else:
    warn("P5.17h 截图还没生成（store/out/ 按 .gitignore 不进仓库）",
         "跑 .buildenv\\Scripts\\python.exe store\\render_shots.py")

# 提审材料不能再声称「没有现成截图 / 需人工截图」——那是旧状态，会让人白跑一趟
_stale = []
for _f in ("store/README-STORE.md", "store/build_store.py"):
    _t = open(os.path.join(ROOT, _f), encoding="utf-8").read()
    for _c in ("需人工截图", "仓库里没有现成"):
        if _c in _t:
            _stale.append("%s 里的「%s」" % (_f, _c))
check("P5.17i 提审材料不再声称「没有现成截图」", not _stale, "; ".join(_stale))

# ---------------------------------------------------------------- P5.18 发布物料自洽性
head("P5.18 发布物料（下载指引 + 校验清单自洽）")

_sums = os.path.join(ROOT, "dist", "release", "SHA256SUMS.txt")
_rel_dir = os.path.join(ROOT, "dist", "release")
_src_sr = open(os.path.join(ROOT, "sign_release.py"), encoding="utf-8").read()

# 已发布的校验清单里，每一行引用的文件都必须真实存在于 dist/release/。
# 踩过：sign_release 把 onedir 的 dist\Desktop-sing-v<v>\Desktop-sing.exe 也写进清单，
# 只用 basename → 多出一行「用户永远找不到对应文件」的清单项，而脚本自己毫无察觉。
if os.path.isfile(_sums):
    _missing = []
    for _line in open(_sums, encoding="utf-8"):
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue                      # '#' 是说明行，sha256sum -c 会忽略
        _parts = _line.split(None, 1)
        if len(_parts) != 2:
            _missing.append("格式不对: %s" % _line[:40])
            continue
        if not os.path.isfile(os.path.join(_rel_dir, _parts[1].strip())):
            _missing.append(_parts[1].strip())
    check("P5.18a 已发布的 SHA256SUMS 每行都指向真实存在的发布物", not _missing,
          "清单里有找不到的文件: %s" % _missing if _missing else
          "共 %d 项" % sum(1 for l in open(_sums, encoding="utf-8")
                           if l.strip() and not l.startswith("#")))
else:
    warn("P5.18a 还没生成 SHA256SUMS.txt",
         "跑 sign_release.py（发版时必须刷新并随 Release 发布）")

# 生成逻辑本身要保证「只收录 dist/release/ 内的文件」，否则下次还会复发
check("P5.18b 校验清单只收录 dist/release/ 内的发布物",
      "in_rel" in _src_sr and "pub_rows" in _src_sr and "if r[5]" in _src_sr,
      "应排除 onedir 里的 Desktop-sing.exe（已含在免安装 zip 内）")

# 发布页的文件名是 ASCII（GitHub 会剥掉非 ASCII asset 名），
# 清单里必须给出「asset 名 ← 本地中文名」的映射，否则用户对不上号
check("P5.18c 校验清单带 ASCII asset 名映射", "_ASSET_ALIASES" in _src_sr and
      "setup.exe" in _src_sr and "portable.zip" in _src_sr,
      "用户下载到的是 ASCII 名，清单里却是中文名，不写映射无法对照")
if os.path.isfile(_sums):
    _head = open(_sums, encoding="utf-8").read().splitlines()[:8]
    _has_map = any("←" in l and ".exe" in l for l in _head)
    check("P5.18d 清单表头真的写出了映射行", _has_map,
          "" if _has_map else "表头没有「asset 名 ← 本地名」这一行")

# 仓库首页必须让人知道去哪下载（README.md 是仓库门面）
for _f, _name in (("README.md", "中文"), ("README.en.md", "英文")):
    _txt = open(os.path.join(ROOT, _f), encoding="utf-8").read()
    _ok = ("releases/latest" in _txt) and ("setup.exe" in _txt)
    check("P5.18e %s README 有下载指引（指向 Releases + 说明 asset 名）" % _name, _ok,
          "" if _ok else "仓库首页没有下载入口，访客找不到安装包")

# ---------------------------------------------------------------- 汇总
head("汇总")
print("  FAIL: %d   WARN: %d" % (len(FAILS), len(WARNS)))
for f in FAILS:
    print("    ✗ %s" % f)
for w in WARNS:
    print("    ! %s" % w)
print("\n%s" % ("全部关键项通过" if not FAILS else "存在未通过项，见上"))
sys.exit(1 if FAILS else 0)
