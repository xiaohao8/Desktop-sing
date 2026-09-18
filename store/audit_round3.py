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
_msix = os.path.join(ROOT, "store", "out", "Desktop-sing-1.0.0.0-x64.msix")
if os.path.exists(_msix):
    import zipfile as _zf
    _names = _zf.ZipFile(_msix).namelist()
    _have = [n for n in _names
             if "LICENSE-THIRD-PARTY" in n or n.endswith("PRIVACY.md")]
    check("P5.12e 已打包的 MSIX 里含许可/隐私声明", bool(_have),
          "找到: %s" % _have if _have else "包内没有 —— 需重新打包")

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

# ---------------------------------------------------------------- 汇总
head("汇总")
print("  FAIL: %d   WARN: %d" % (len(FAILS), len(WARNS)))
for f in FAILS:
    print("    ✗ %s" % f)
for w in WARNS:
    print("    ! %s" % w)
print("\n%s" % ("全部关键项通过" if not FAILS else "存在未通过项，见上"))
sys.exit(1 if FAILS else 0)
