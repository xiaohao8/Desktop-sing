# -*- coding: utf-8 -*-
"""把 PyInstaller onedir 产物打成 Microsoft Store 用的 MSIX 包。

    .buildenv\\Scripts\\python.exe store\\build_store.py                # 用现有 dist 产物打包
    .buildenv\\Scripts\\python.exe store\\build_store.py --fresh        # 先重跑 build_exe --dir 再打包
    .buildenv\\Scripts\\python.exe store\\build_store.py --wack         # 打完顺带跑 WACK（需管理员）

包标识（Identity Name / Publisher）必须来自 Partner Center，读三处、优先级从高到低：
    1) 命令行 --name / --publisher
    2) store/identity.local.json      （本机填一次即可，勿提交仓库）
    3) 占位值                          （能出包，仅供本地看结构，**不能上传**）

隐私政策站点根地址（--site-url 或 identity.local.json 的 "site_url"）用来把提审文案里的
`/privacy.html`、`/privacy.en.html` 填成真实地址 —— 政策 10.5.1 要求 Win32 / Desktop Bridge
产品必须始终具备隐私政策，缺 URL 直接拒审。identity.local.json 完整长这样：

    {
      "name": "12345Desktop-sing",
      "publisher": "CN=1A2B3C4D-5E6F-...",
      "site_url": "https://xxx.netlify.app"
    }

输出：store/out/Desktop-sing-<版本>-x64.msix（未签名——Store 提审就传未签名包，
      微软会用它自己的证书重签；本地自签测试见 README-STORE.md）。
"""
import argparse
import io
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
LAYOUT = os.path.join(BASE, "build", "layout")
OUTDIR = os.path.join(BASE, "out")
TEMPLATE = os.path.join(BASE, "AppxManifest.template.xml")
IDENTITY_LOCAL = os.path.join(BASE, "identity.local.json")

MAKEAPPX = r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe"
WACK = r"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe"

# 清单里的应用名（Properties/DisplayName 与 VisualElements/@DisplayName）。
#
# ⚠️ 商店硬要求：这个字符串必须是**你在 Partner Center 预留过的名字之一**，否则上传后报
#    「The name found in the package is not one of your reserved app names」
#    （官方文档 MSIX《解决提交错误》的「名称/标识错误」条目）。
#    真源是 Partner Center 的「产品管理 → 管理应用名称预留」页，**逐字符照抄**。
#    可用 identity.local.json 的 display_name 或命令行 --display-name 覆盖。
#
# 值＝本应用预留的名字：「桌面歌词|Desktop-sing」（中英并排，商店商品名与 Start 菜单都用它）。
# ShortName 是磁贴底部那行短字，不受预留名校验，保持简短即可。
DISPLAY_NAME = "桌面歌词|Desktop-sing"
SHORT_NAME = "桌面歌词"        # 磁贴底部短名称（全名过长会被截断）

# 清单 <Properties><PublisherDisplayName>。
# ⚠️ 与 Identity 一样受 Partner Center 校验：必须**逐字符等于**
#    「产品标识」页给出的 `Package/Properties/PublisherDisplayName`，
#    否则报「应用清单中的 PublisherDisplayName 元素 … 与发布者显示名称不匹配」。
#    真源是账号的发布者显示名（个人账号通常是真实姓名），**不要写成产品名**。
#    可用 identity.local.json 的 publisher_display_name 或命令行覆盖。
PUBLISHER_DISPLAY_NAME = "Desktop-sing Project"

# 清单里的 Description（uap:VisualElements/@Description）：
# 商店策略 10.1.1 要求准确描述「重要限制」。这里把限制写全，
# 免得审核员按描述预期去测却发现对不上。
#
# ⚠️ 这一串会被写进用户可见的清单，**同样受 10.1.1 / 11.2 约束**：
#    不点名任何第三方品牌（旧版写了「如 QQ音乐 / 网易云音乐 / 酷狗音乐」，
#    等于把商标写进包元数据）。要说明兼容性就描述「接入 SMTC」这一客观事实。
DESCRIPTION = ("播放器式桌面歌词应用：主窗口提供最近播放、全屏歌词舞台、播放历史与本机听歌报告，"
               "桌面歌词条作为迷你模式保留；通过 Windows 系统媒体控制（SMTC）遥控当前媒体会话"
               "并显示逐字歌词，不直接播放本地音频文件。"
               "支持 5 种悬浮样式、9 种逐字动画、4 种氛围屏保、14 款配色主题（可固定主题"
               "或跟随封面主色自动换肤）、翻译与音译显示、进度时间、全局快捷键（默认关闭）"
               "与开机自启（默认关闭）。"
               "听歌统计仅保存在本机，单次不足 20 秒不记录，可关闭或清空；"
               "无账号、无广告、无追踪。")

# 商店商品页「描述」字段（比清单 Description 长，可分段）。
# 受 10.1.1（准确描述重要限制）与 10.7（本地化：界面只有中文需如实说明）约束。
#
# ⚠️ 功能数量必须与代码一致，且与主程序「关于」窗口、官网口径统一。
#    真源：STYLE_NAMES(5) / ANIM_STYLES(9) / saver_style(4) / POSITION_PRESETS(7)。
#    写数字前先数一遍，别凭印象——数字对不上审核员会当成虚假描述。
STORE_LISTING_DESCRIPTION = """桌面歌词是一款播放器式桌面歌词应用：左侧是最近播放与功能导航，右侧是全屏歌词舞台，并附带播放历史与本机听歌报告；桌面歌词条保留为迷你模式。

【主要功能】
· 播放器主界面：最近播放、全屏歌词舞台、沉浸模式、播放 / 暂停、上下首与进度跳转
· 本机听歌报告与播放历史：本月 / 今日时长、连续听歌、活跃天数、最爱时段、常听歌手与热门歌曲
· 逐字卡拉OK歌词：匹配系统正在播放的歌曲，并从多个公开歌词来源择优显示
· 5 种悬浮样式 · 9 种逐字动画 · 柔和描边（浅色深色壁纸都清晰）
· 14 款配色主题（v2.0 新增）：固定主题或跟随封面主色自动换肤，悬浮条 / 光晕 / 屏保 / 面板配色同步
· 4 种氛围屏保（3D 粒子 / 极简时钟 / 音浪 / 星轨）：长时间空闲自动进入黑底防烧屏画面
· 翻译与音译歌词 · 进度时间
· 摆放位置预设（7 个锚点，换分辨率也贴边）· 可锁定位置防误拖
· 全局快捷键（默认关闭，可在设置里开启）
· 开机自启（默认关闭，可在系统「设置 → 应用 → 启动」里开启）

【使用前提（重要限制）】
· 仅支持 Windows 10（1809 及以上）/ Windows 11，仅 x64
· 播放器界面通过 SMTC 遥控当前系统媒体会话，不直接播放本地音频文件
· 歌词信息来自 Windows 系统媒体控制（SMTC）：播放器必须接入 SMTC 才能读取当前歌曲，VR 类或老式播放器可能读不到
· 同时打开多个播放器时，跟随正在播放的那一个
· 需要联网才能获取歌词；已获取的歌词会缓存在本机，断网时可继续显示
· 界面语言：简体中文 / 繁體中文 / English / 日本語（设置内可切换，默认跟随系统）

【隐私】
程序没有账号系统、没有广告、没有统计埋点，不收集任何个人身份信息。设置、歌词缓存、日志与听歌统计全部保存在本机 %APPDATA%\\Desktop-sing\\ 目录，不上传任何服务器。听歌统计仅含歌名、歌手、日期、小时、播放秒数、播放次数与最近播放时间，不保存专辑、播放器来源、文件路径、账号、设备 ID 或 IP；单次不足 20 秒不记录，默认开启，可关闭或一键清空。程序不提供音乐库、推荐流或第三方账号登录；仅在匹配当前歌曲歌词时，按需向上述歌词来源发送歌曲名 / 歌手名 / 时长。

【关于更新】
Microsoft Store 版本由商店统一分发更新，程序内不含任何自更新通道。"""

# 清单 Resources 声明的界面语言（2026-11-14 起四语言）。
# ⚠️ 必须与 store/AppxManifest.template.xml 的 <Resource Language> 一致，
#    write_manifest 会自检；Partner Center 的 Store listing 也要为每种语言
#    配套填写描述（见 LISTING_DESCRIPTIONS / listing-v*.md 的四语言块）。
SUPPORTED_LANGS = ("zh-CN", "zh-TW", "en-US", "ja-JP")

# 各语言商店商品页「描述」。zh-CN 与 STORE_LISTING_DESCRIPTION 同源；
# 其余语言为人工翻译版（语义一致，数字/限制口径不变）。
LISTING_DESCRIPTIONS = {
    "zh-CN": STORE_LISTING_DESCRIPTION,
    "zh-TW": """桌面歌詞是一款播放器式桌面歌詞應用：左側是最近播放與功能導覽，右側是全螢幕歌詞舞台，並附帶播放歷史與本機聽歌報告；桌面歌詞條保留為迷你模式。

【主要功能】
· 播放器主介面：最近播放、全螢幕歌詞舞台、沉浸模式、播放 / 暫停、上下首與進度跳轉
· 本機聽歌報告與播放歷史：本月 / 今日時長、連續聽歌、活躍天數、最愛時段、常聽歌手與熱門歌曲
· 逐字卡拉OK歌詞：匹配系統目前播放的歌曲，並從多個公開歌詞來源擇優顯示
· 5 種懸浮樣式 · 9 種逐字動畫 · 柔和描邊（淺色深色桌布都清晰）
· 14 款配色主題（v2.0 新增）：固定主題或跟隨封面主色自動換膚，懸浮條 / 光暈 / 螢保 / 面板配色同步
· 4 種氛圍螢保（3D 粒子 / 極簡時鐘 / 音浪 / 星軌）：長時間閒置自動進入黑底防燒屏畫面
· 翻譯與羅馬音歌詞 · 歌詞繁簡轉換 · 進度時間
· 擺放位置預設（7 個錨點，換解析度也貼邊）· 可鎖定位置防誤拖
· 全域快捷鍵（預設關閉，可在設定裡開啟）
· 開機自啟（預設關閉，可在系統「設定 → 應用程式 → 啟動」裡開啟）

【使用前提（重要限制）】
· 僅支援 Windows 10（1809 及以上）/ Windows 11，僅 x64
· 播放器介面透過 SMTC 遙控目前系統媒體工作階段，不直接播放本機音訊檔案
· 歌詞資訊來自 Windows 系統媒體控制（SMTC）：播放器必須接入 SMTC 才能讀取當前歌曲，VR 類或老式播放器可能讀不到
· 同時開啟多個播放器時，跟隨正在播放的那一個
· 需要連網才能取得歌詞；已取得的歌詞會快取在本機，斷網時可繼續顯示
· 介面語言：繁體中文 / 簡體中文 / English / 日本語（設定內可切換，預設跟隨系統）

【隱私】
程式沒有帳號系統、沒有廣告、沒有統計埋點，不收集任何個人身份資訊。設定、歌詞快取、日誌與聽歌統計全部保存在本機 %APPDATA%\\Desktop-sing\\ 目錄，不上傳任何伺服器。聽歌統計僅含歌名、歌手、日期、小時、播放秒數、播放次數與最近播放時間，不保存專輯、播放器來源、檔案路徑、帳號、裝置 ID 或 IP；單次不足 20 秒不記錄，預設開啟，可關閉或一鍵清空。程式不提供音樂庫、推薦流或第三方帳號登入；僅在匹配目前歌曲歌詞時，按需向歌詞來源發送歌曲名 / 歌手名 / 時長。

【關於更新】
Microsoft Store 版本由商店統一分發更新，程式內不含任何自更新通道。""",
    "en-US": """Desktop-sing is a player-style desktop lyrics app: recently played tracks and
navigation on the left, a full-screen lyric stage on the right, plus playback history and an
on-device listening report. The desktop lyric bar remains as mini mode.

[Features]
- Player window: recently played tracks, full-screen lyric stage, immersive mode,
  play/pause, previous/next and seek
- On-device listening report and history: monthly/today totals, streaks, active days,
  peak hour, top artists and top tracks
- Word-by-word karaoke lyrics matched to the song the system is already playing, with
  several public lyric sources and the best version winning
- 5 overlay styles, 9 word-by-word animations, soft outline (clear on light and dark walls)
- 14 color themes (new in v2.0): fixed palette or auto-tinted from the album cover;
  bar / glow / screensaver / settings all follow
- 4 ambient screensavers (3D particles / minimal clock / sound bars / star trails),
  auto-entered when idle, black background, burn-in safe
- Translation and romanization lines, traditional-simplified conversion, progress time
- Position presets (7 anchors, multi-monitor safe) and lockable placement
- Global hotkeys (off by default) and run-at-startup (off by default)

[Before you use (important limits)]
- Windows 10 (1809+) / Windows 11 only, x64 only
- The player window controls the current system media session through SMTC; it does not
  play local audio files directly
- Song info comes from Windows system media controls (SMTC): a player must integrate
  SMTC for the app to see it; VR-type or legacy players may not work
- With several players open, the app follows the one that is playing
- Internet is required to fetch lyrics; fetched lyrics are cached locally and remain
  available offline
- UI languages: Traditional Chinese / Simplified Chinese / English / Japanese
  (auto-detected from system locale, switchable in Settings)

[Privacy]
No account, no ads, no analytics, no personal data collected. Settings, lyric cache,
logs and listening statistics stay in %APPDATA%\\Desktop-sing\\ on your machine.
No music library, recommendation feed or third-party account login is included. Listening statistics contain only track title, artist, date, hour, played seconds,
play count and last-played time - no album, player source, file paths, account, device
ID or IP address. Sessions under 20 seconds are ignored. The feature is on by default
and can be disabled or cleared. Matching lyrics only sends the song title / artist /
duration to public lyric sources.

[Updates]
The Store build is updated by Microsoft Store; the app contains no self-update channel.""",
    "ja-JP": """Desktop-sing はプレーヤー形式のデスクトップ歌詞アプリです。左側に最近再生した曲と
ナビゲーション、右側に全画面の歌詞ステージを配置し、再生履歴とローカル視聴レポートも備えます。
デスクトップ歌詞バーはミニモードとして残ります。

【主な機能】
· プレーヤー画面：最近再生、全画面歌詞ステージ、没入モード、再生 / 一時停止、前後の曲、シーク
· ローカル視聴レポートと再生履歴：今月 / 今日の時間、連続視聴、利用日数、よく聴く時間帯、
  よく聴くアーティストと曲
· ワード単位カラオケ歌詞：システムで再生中の曲に一致する歌詞を複数の公開ソースから取得し、
  最良の版を自動選択
· オーバーレイスタイル 5 種 · ワードアニメーション 9 種 · ソフトアウトライン（明暗どちらも鮮明）
· カラーテーマ 14 種（v2.0 で追加）：固定パレット or アルバムカバーからの自動配色
  （バー / グロー / スクリーンセーバー / 設定画面が連動）
· スクリーンセーバー 4 種（3D パーティクル / ミニマル時計 / サウンドバー / 星の軌跡）：
  アイドル時に自動開始、黒背景で焼き付き防止
· 翻訳・ローマ字表示、繁体字⇔簡体字変換、再生時間表示
· 位置プリセット（7 アンカー、マルチモニター対応）と配置ロック
· グローバルホットキー（既定オフ）、起動時に実行（既定オフ）

【使用条件（重要な制限）】
· Windows 10（1809 以降）/ Windows 11 専用、x64 のみ
· プレーヤー画面は SMTC 経由で現在のシステムメディアセッションを操作します。
  ローカル音声ファイルを直接再生する機能はありません
· 曲情報は Windows のシステムメディアコントロール（SMTC）から取得：SMTC 対応の
  プレーヤーのみ読み取れます（VR 系や古いプレーヤーは不可の場合あり）
· 複数のプレーヤーを開いている場合は再生中のものに追従
· 歌詞の取得にはインターネットが必要。取得済みの歌詞はローカルにキャッシュされ、
  オフラインでも表示できます
· 表示言語：繁体字中国語 / 簡体字中国語 / English / 日本語（システム設定に追従、設定で切替可）

【プライバシー】
アカウントなし、広告なし、トラッキングなし。個人情報は収集しません。設定・歌詞キャッシュ・
ログ・視聴統計はすべて %APPDATA%\\Desktop-sing\\ に保存され、サーバーへ送信されません。
視聴統計に含まれるのは曲名、アーティスト、日付、時刻、再生秒数、再生回数、最終再生時刻のみで、
アルバム、再生元、ファイルパス、アカウント、端末 ID、IP は保存しません。20 秒未満は記録せず、
既定で有効、設定で無効化または消去できます。音楽ライブラリ、推薦フィード、第三者アカウント
ログインは提供しません。歌詞照合時には曲名 / 歌手名 / 長さのみを歌詞ソースに送信します。

【更新について】
ストア版の更新は Microsoft Store が配信します。アプリ内に自己更新経路はありません。""",
}



# ---------------- 四语言搜索词（Partner Center 每个 listing 语言各有一组） ----------------
# 规则：≤7 个；不得写价格/折扣词；**不得使用他人品牌名**（写「QQ音乐」「网易云」
# 会被 11.2「不得侵犯第三方权利」打回，也会让人觉得有官方关联）。
# 中文用的是自家产品名与品类词，安全。
LISTING_SEARCH_TERMS = {
    "zh-CN": ("桌面歌词", "歌词", "悬浮歌词", "卡拉OK", "逐字歌词", "桌面工具", "音乐"),
    "zh-TW": ("桌面歌詞", "歌詞", "懸浮歌詞", "卡拉OK", "逐字歌詞", "桌面工具", "音樂"),
    "en-US": ("lyrics", "desktop lyrics", "karaoke", "synced lyrics",
              "lyric overlay", "now playing", "music"),
    "ja-JP": ("歌詞", "デスクトップ歌詞", "カラオケ", "同期歌詞", "オーバーレイ",
              "再生中", "音楽"),
}

# ---------------- 四语言「此版本中的更改」 ----------------
# 同样是**逐语言**字段。zh-CN 优先取 update.json（与程序内更新弹窗同一份口径），
# update.json 没跟上版本时回落到这里；其余语言没有对应渠道，恒用本表。
# ⚠️ 改版时必须同步改：数字/功能名要与代码一致，别写未做的功能（10.1.1）。
LISTING_WHATS_NEW = {
    "zh-CN": (
        "【新增】播放器主界面：最近播放、全屏歌词舞台、沉浸模式、播放 / 暂停、上下首与进度跳转",
        "【新增】播放历史与本机听歌报告：本月 / 今日时长、连续听歌、活跃天数、最爱时段、常听歌手与热门歌曲；不足 20 秒不记录，可关闭或清空",
        "【优化】桌面歌词条保留为迷你模式；普通启动打开播放器，登录自启只显示迷你歌词条",
        "【修复】主播放器进度条不可见、20 秒级听歌记录显示为 0 分钟、清空统计后旧数据可能回写",
    ),
    "zh-TW": (
        "【新增】播放器主介面：最近播放、全螢幕歌詞舞台、沉浸模式、播放 / 暫停、上下首與進度跳轉",
        "【新增】播放歷史與本機聽歌報告：本月 / 今日時長、連續聽歌、活躍天數、最愛時段、常聽歌手與熱門歌曲；不足 20 秒不記錄，可關閉或清空",
        "【優化】桌面歌詞條保留為迷你模式；一般啟動開啟播放器，登入自啟只顯示迷你歌詞條",
        "【修復】主播放器進度條不可見、20 秒級聽歌記錄顯示為 0 分鐘、清空統計後舊資料可能回寫",
    ),
    "en-US": (
        "New: player window with recently played tracks, a full-screen lyric stage, immersive mode, "
        "play/pause, previous/next and seeking.",
        "New: playback history and an on-device listening report with monthly/today totals, streaks, "
        "active days, peak hour, top artists and top tracks. Sessions under 20 seconds are ignored; "
        "the feature can be disabled or cleared.",
        "Improved: the desktop lyric bar remains as mini mode. A normal launch opens the player; "
        "logon startup shows only the mini bar.",
        "Fixed: the player progress bar was invisible, 20-second sessions showed as 0 minutes, and "
        "cleared listening data could be written back.",
    ),
    "ja-JP": (
        "新機能：プレーヤー画面（最近再生、全画面歌詞ステージ、没入モード、再生 / 一時停止、"
        "前後の曲、シーク）。",
        "新機能：再生履歴とローカル視聴レポート（今月 / 今日の時間、連続視聴、利用日数、"
        "よく聴く時間帯、アーティスト、曲）。20 秒未満は記録せず、無効化・消去も可能です。",
        "改善：デスクトップ歌詞バーはミニモードとして維持。通常起動ではプレーヤーを開き、"
        "ログオン時の自動起動ではミニバーのみ表示します。",
        "修正：プレーヤーの進行バーが非表示、20 秒の視聴が 0 分表示、消去した視聴データが"
        "書き戻される可能性があった問題。",
    ),
}


def listing_selfcheck():
    """提审前自检：四语言三张表必须齐全，搜索词不超限。

    Partner Center 的 listing 是逐语言表单，少一种语言的描述/搜索词/更新说明
    就是那份表单只能空着交（信息不全），而脚本不会自己报错 —— 所以在出口
    处硬性拦一道，别指望临场记得。
    """
    bad = []
    for lg in SUPPORTED_LANGS:
        if lg not in LISTING_DESCRIPTIONS or not LISTING_DESCRIPTIONS[lg].strip():
            bad.append("%s 缺商品页描述" % lg)
        terms = LISTING_SEARCH_TERMS.get(lg) or ()
        if not terms:
            bad.append("%s 缺搜索词" % lg)
        elif len(terms) > 7:
            bad.append("%s 搜索词 %d 个（上限 7）" % (lg, len(terms)))
        notes = LISTING_WHATS_NEW.get(lg) or ()
        if not notes:
            bad.append("%s 缺「此版本中的更改」" % lg)
    if bad:
        raise SystemExit("提审材料不完整：" + "；".join(bad))
    print("[自检] 四语言描述 / 搜索词 / 更新说明齐全")

# 提审时填「受限功能说明」用（runFullTrust）。Partner Center 该字段长度有限，
# 长文案会被静默截断，所以这里只给两句。
RUNFULLTRUST_STATEMENT = (
    "本应用是 Win32 桌面程序（PySide6 打包），需要读取 Windows 系统媒体控制"
    "（SMTC）提供的当前播放信息、在无边框透明窗口上绘制歌词，并使用全局快捷键、"
    "系统托盘与开机自启项，这些必须运行在完全信任模式下。"
    "应用不修改系统文件，不安装其他软件，所有数据仅保存在本机用户目录。")

# 提审时填「认证说明」（Notes for certification）。帮审核员知道怎么测。
# ⚠️ 必须英文在前：上次提审（v1.0.0）因纯中文说明 + 静态待机卡被误判为
#    「The product loads indefinitely at launch」（10.1.2.10）拒审。
#    英文第一句必须点破「普通启动会打开真实主播放器窗口，不是加载画面」。
CERTIFICATION_NOTES = """[English]
Test guide for Desktop-sing v{version}:
1. NORMAL LAUNCH OPENS A MAIN PLAYER WINDOW. It contains a sidebar with
   recently played tracks, a full-screen lyric stage, playback history and an
   on-device listening report. The small desktop lyric bar remains available
   as "mini mode" (title-bar button or tray menu). This is a real window, not
   a loading screen. On a logon/startupTask launch the app intentionally opens
   only the mini bar.
2. No account, no sign-in required. Internet access is needed to fetch lyrics.
3. To see lyrics (the core feature): play any song in a player that supports
   Windows system media controls (SMTC) — e.g. the built-in Windows "Media
   Player" app with any local audio file. Lyrics then appear automatically
   in the player window and on the mini bar. The player window controls the
   current SMTC session; it does not play local audio files itself. If no
   player is playing, the UI stays in the "Ready" state by design.
4. Right-click the tray icon to open Settings. Global hotkeys are OFF by
   default (to avoid conflicts), so Ctrl+Alt+S does nothing until enabled in
   Settings — this is intentional, not a malfunction.
5. Updates are distributed by Microsoft Store; the app contains no self-update.
6. UI language: Simplified Chinese / Traditional Chinese / English / Japanese
   (auto-detected from system locale; switchable in Settings > Language).
   All four are fully translated - no leftover Chinese in the English,
   Japanese or Traditional Chinese UI.
7. Per-language screenshots are attached to each listing language. If a
   screenshot does not match the language you are reviewing, switch the
   language in Settings > Language to reproduce it.
8. Listening statistics are local-only and on by default. They contain only
   title, artist, date, hour, played seconds, play count and last-played time;
   no album, player source, path, account, device ID or IP. Sessions under
   20 seconds are ignored. The user can disable or clear them in Settings.

[中文]
桌面歌词 v{version} 测试指引：
1. 普通启动会打开播放器主窗口：左侧为最近播放与导航，右侧为全屏歌词舞台，
   并包含播放历史与本机听歌报告。桌面歌词条保留为「迷你模式」（标题栏按钮
   或托盘菜单切换）。这是真实窗口，不是加载画面；登录自启时只显示迷你条。
2. 无账号、无需登录；获取歌词需要联网。
3. 查看歌词（核心功能）：用任意接入 Windows 系统媒体控制（SMTC）的播放器
   播放歌曲，例如用系统自带「媒体播放器」打开任意本地音频文件，歌词会自动
   显示在播放器窗口和迷你歌词条上。播放器窗口通过 SMTC 遥控当前媒体会话，
   本身不直接播放本地音频文件。没有播放器在播歌时保持「已就绪」待机态，
   属预期行为，不是卡死。
4. 右键点击系统托盘图标 → 菜单选「设置…」即可打开设置面板。
   全局快捷键默认关闭（避免与其他软件抢键），
   Ctrl+Alt+S 初始状态下无效属预期，可在设置面板开启。
5. 更新由 Microsoft Store 统一分发，程序内没有自更新通道。
6. 听歌统计仅保存在本机，默认开启，仅含歌名、歌手、日期、小时、播放秒数、
   播放次数与最近播放时间；不含专辑、播放器来源、文件路径、账号、设备 ID 或 IP。
   单次不足 20 秒不记录，可在设置中关闭或清空。"""

# 商店版不要带的文件（卸载器没有意义：商店应用从系统设置里卸载）
#
# watchdog.exe 也排除：商店版 STORE_MODE 下保活整体禁用
# （lyrics_overlay.py 的 spawn_supervisor 直接 return），这个原生 exe 在包里
# 永远不会被拉起，却多出一个「未签名的 CreateProcess 型小工具」给杀软扫。
# 便携版/安装版仍由 build_exe.py 附带，功能不受影响。
EXCLUDE_FILES = {"卸载桌面歌词.bat", "watchdog.exe"}

# 必须随包分发的许可/声明文件。
# 为什么不能只放在仓库里：Apache-2.0 第 4 条要求「向接收者提供一份 NOTICE」，
# 内置的 MiSans 也要求保留许可说明。商店用户只拿到 .msix，看不到 GitHub 仓库，
# 所以这些文件必须真的进包，否则是实打实的许可违规。
# （来源：仓库根目录，打包时复制到程序目录，用户可在安装目录里查看。）
#
# 中英各一份：Microsoft Store 是全球分发的，商店页/审核语言可能是英文，
# 只给中文声明等于英文用户拿不到可读的隐私说明。
# 使用说明也一并带上：MSIX 的布局来自 onedir，而 onedir 里**没有**使用说明，
# 早先只有便携版/安装版才有 → 商店用户装完找不到任何使用说明，两条渠道不一致。
# 随包文档：(仓库源文件名, 落包文件名)。
# 落包名用 ASCII：makeappx 会把包内**非 ASCII 文件名百分号编码**
# （使用说明.txt → %E4%BD%BF…txt），虽 Windows 安装后会解码回原名、审计也用 unquote 兼容，
# 但落包直接给 ASCII 名（USAGE-zh.txt）更干净、零歧义。仓库根目录仍保留中文名，
# 供便携版/安装版（不走 makeappx）沿用，两条渠道内容一致、只是文件名不同。
BUNDLED_LICENSES = (("LICENSE-THIRD-PARTY.txt", "LICENSE-THIRD-PARTY.txt"),
                    ("PRIVACY.md", "PRIVACY.md"),
                    ("使用说明.txt", "USAGE-zh.txt"),
                    ("PRIVACY.en.md", "PRIVACY.en.md"),
                    ("USAGE.en.txt", "USAGE.en.txt"))


def app_version() -> str:
    """从主程序读 APP_VERSION（省得两处维护）。"""
    txt = open(os.path.join(ROOT, "lyrics_overlay.py"), encoding="utf-8").read()
    for line in txt.splitlines():
        if line.startswith("APP_VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("lyrics_overlay.py 里没找到 APP_VERSION")


def run_com_audit():
    """构建前先跑 COM/WinRT 隔离静态审计（2026-11-13 商店版挂死事故的门禁）。"""
    import subprocess
    audit_py = os.path.join(ROOT, "tools", "audit_com_isolation.py")
    r = subprocess.run([sys.executable, "-I", audit_py],
                       capture_output=True, encoding="utf-8", errors="ignore")
    for line in ((r.stdout or "") + (r.stderr or "")).strip().splitlines():
        safe = line.encode(sys.stdout.encoding or "utf-8",
                           errors="replace").decode(sys.stdout.encoding or "utf-8")
        print("  [审计] " + safe)
    if r.returncode != 0:
        raise SystemExit("COM 隔离审计未通过：禁止打包（详见 tools/audit_com_isolation.py）")


def package_version(v: str) -> str:
    """MSIX 版本必须是 4 段数字（1.0.0 → 1.0.0.0）。"""
    parts = [p for p in v.strip().split(".") if p != ""]
    if len(parts) > 4:
        parts = parts[:4]
    while len(parts) < 4:
        parts.append("0")
    if not all(p.isdigit() for p in parts):
        raise SystemExit("版本号只能是数字：%s" % v)
    return ".".join(parts)


def load_identity(args):
    """按 命令行 → identity.local.json → 占位 的优先级取标识。"""
    name, publisher = args.name, args.publisher
    if (not name or not publisher) and os.path.isfile(IDENTITY_LOCAL):
        try:
            cfg = json.load(open(IDENTITY_LOCAL, encoding="utf-8"))
            name = name or cfg.get("name", "")
            publisher = publisher or cfg.get("publisher", "")
        except Exception as ex:
            print("[警告] identity.local.json 解析失败：%s" % ex)
    name = name or "Desktop-sing-PLACEHOLDER"
    publisher = publisher or "CN=PLACEHOLDER-FILL-ME"
    return name, publisher


def load_display_name(args) -> str:
    """清单里的应用名：命令行 --display-name → identity.local.json 的 display_name → 常量。

    ⚠️ 必须是 Partner Center **预留过的名字之一**（逐字符），否则上传即被拒：
    「The name found in the package is not one of your reserved app names」。
    """
    nm = (getattr(args, "display_name", "") or "").strip()
    if not nm and os.path.isfile(IDENTITY_LOCAL):
        try:
            with open(IDENTITY_LOCAL, encoding="utf-8") as f:
                nm = (json.load(f).get("display_name", "") or "").strip()
        except Exception as ex:
            print("[警告] identity.local.json 解析失败：%s" % ex)
    return nm or DISPLAY_NAME


def load_publisher_display_name(args) -> str:
    """清单里的发布者显示名：命令行 → identity.local.json 的 publisher_display_name → 常量。

    与 Identity 一样要被 Partner Center 逐字符校验（见 PUBLISHER_DISPLAY_NAME 注释）。
    """
    nm = (getattr(args, "publisher_display_name", "") or "").strip()
    if not nm and os.path.isfile(IDENTITY_LOCAL):
        try:
            with open(IDENTITY_LOCAL, encoding="utf-8") as f:
                nm = (json.load(f).get("publisher_display_name", "") or "").strip()
        except Exception as ex:
            print("[警告] identity.local.json 解析失败：%s" % ex)
    return nm or PUBLISHER_DISPLAY_NAME


def load_site_url(args) -> str:
    """隐私政策页所在的**站点根地址**：命令行 --site-url → identity.local.json 的 site_url。

    商店表单里中英文 listing 要分别填 `/privacy.html` 与 `/privacy.en.html`（政策 10.5.1
    硬要求，缺 URL 直接拒审），所以把站点根写在一处，出包与提审文案都不会漏填。
    返回已去掉末尾 `/` 的地址；没配就返回空串。
    """
    url = (getattr(args, "site_url", "") or "").strip()
    if not url and os.path.isfile(IDENTITY_LOCAL):
        try:
            with open(IDENTITY_LOCAL, encoding="utf-8") as f:
                url = (json.load(f).get("site_url", "") or "").strip()
        except Exception as ex:
            print("[警告] identity.local.json 解析失败：%s" % ex)
    return url.rstrip("/")


def stage_layout(version: str = ""):
    """组装 MSIX 布局：清单 + 资产 + onedir 程序本体（去掉商店版不该带的文件）。"""
    # 布局版本必须与将要写进清单的版本一致：以前这里在目录缺失时回退到一个
    # 写死的旧 onedir，结果把旧产物（旧 Python 运行时、旧 exe 哈希）打进新号包里。
    # 现在只认目标版本目录，缺就直接失败，宁可不打包也不出错包。
    ver = version or app_version()
    onedir = os.path.join(ROOT, "dist", "Desktop-sing-v%s" % ver)
    exe = os.path.join(onedir, "Desktop-sing.exe")
    if not (os.path.isdir(onedir) and os.path.isfile(exe)):
        raise SystemExit(
            "没找到 v%s 的完整 onedir：%s\n"
            "  先跑 .buildenv312\\Scripts\\python.exe build_exe.py --dir，"
            "或给本脚本加 --fresh。\n"
            "  注意：不要靠回退旧目录出包——那会把旧构建打进新版本号里。"
            % (ver, onedir))
    # 布局目录每次重建。沙箱会拦批量删除，用「改名归档」代替 rm -rf
    if os.path.isdir(LAYOUT):
        os.rename(LAYOUT, LAYOUT + ".old-%d" % int(os.path.getmtime(LAYOUT)))
    app_dir = os.path.join(LAYOUT, "Desktop-sing")
    os.makedirs(app_dir, exist_ok=True)
    # 优先硬链接、失败再拷贝：本机 Windows Defender 实时防护会**秒删**刚「拷贝出来」的
    # 未签名 PyInstaller exe（误报），导致 makeappx 报「清单里的 Desktop-sing.exe 不在包内」。
    # dist 原始 exe 已获 Defender 放行，硬链接与它共享同一份数据即可绕过误杀；同时比深拷贝快得多。
    # 个别跨设备/不支持硬链接的情形回退到 copyfile（只拷字节，不 copymode，避开 WinError 5）。
    def _link_or_copy(src, dst):
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)
    shutil.copytree(onedir, app_dir, dirs_exist_ok=True, copy_function=_link_or_copy)
    for f in EXCLUDE_FILES:
        p = os.path.join(app_dir, f)
        if os.path.isfile(p):
            os.remove(p)

    # 许可与隐私声明必须随包（见 BUNDLED_LICENSES 注释）
    for src_name, dst_name in BUNDLED_LICENSES:
        src = os.path.join(ROOT, src_name)
        if not os.path.isfile(src):
            raise SystemExit("缺少随包声明文件：%s（许可合规要求，不能省）" % src_name)
        shutil.copyfile(src, os.path.join(app_dir, dst_name))
        print("  [声明] 已随包 %s" % dst_name)
    assets_dst = os.path.join(LAYOUT, "Assets")
    os.makedirs(assets_dst, exist_ok=True)
    import make_store_assets
    src_assets = os.path.join(BASE, "assets")
    if not os.path.isdir(src_assets) or not make_store_assets.verify(src_assets):
        print("[资产] 缺失或尺寸不对，重新生成…")
        make_store_assets.generate()
    for name in os.listdir(src_assets):
        shutil.copyfile(os.path.join(src_assets, name), os.path.join(assets_dst, name))
    return LAYOUT


def write_manifest(name: str, publisher: str, version: str,
                   display_name: str = "", publisher_display_name: str = "") -> str:
    tpl = open(TEMPLATE, encoding="utf-8").read()
    out = (tpl.replace("{{IDENTITY_NAME}}", name)
              .replace("{{PUBLISHER}}", publisher)
              .replace("{{VERSION}}", version)
              .replace("{{DISPLAY_NAME}}", display_name or DISPLAY_NAME)
              .replace("{{SHORT_NAME}}", SHORT_NAME)
              .replace("{{PUBLISHER_DISPLAY_NAME}}",
                       publisher_display_name or PUBLISHER_DISPLAY_NAME)
              .replace("{{DESCRIPTION}}", DESCRIPTION))
    # 模板注释里有「{{占位符}}」之类的说明文字，发布清单不需要它们——
    # 剥掉全部 XML 注释，顺带把多出来的空行收干净
    out = re.sub(r"<!--.*?-->", "", out, flags=re.S)
    out = re.sub(r"\n\s*\n+", "\n\n", out).strip() + "\n"
    # 多语言自检（2026-11-14）：清单 Resources 必须与 SUPPORTED_LANGS 一致——
    # 多声明了用户会预期该语言 UI，少声明了商店不给对应语言露出。
    declared = re.findall(r'<Resource\s+Language="([^"]+)"\s*/>', out)
    if sorted(declared) != sorted(SUPPORTED_LANGS):
        raise SystemExit("清单 Resources 语言声明 %s 与 SUPPORTED_LANGS %s 不一致"
                         % (declared, list(SUPPORTED_LANGS)))
    path = os.path.join(LAYOUT, "AppxManifest.xml")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(out)
    return path


def run_makeappx(msix_path: str) -> bool:
    cmd = [MAKEAPPX, "pack", "/d", LAYOUT, "/p", msix_path, "/v"]
    print("[打包] %s" % " ".join(cmd[:6]) + " …")
    r = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    out = (r.stdout or "") + (r.stderr or "")
    # /v 的逐文件日志没价值，只看错误/警告和结果行
    # （带冒号才匹配——否则 api-ms-win-core-errorhandling 这类 DLL 名会误中）
    keys = ("error:", "Error:", "ERROR:", "warning:", "Warning:", "Package creation")
    for l in out.splitlines():
        if any(k in l for k in keys):
            print("   " + l)
    if r.returncode != 0:
        print(out[-1500:])
        return False
    return True


def verify_msix(msix_path: str, identity_is_placeholder: bool) -> bool:
    """出包后的自检：结构完整 + 关键文件都在 + 清单引用资产齐全 + 大小合理。"""
    import re
    import zipfile
    ok = True
    with zipfile.ZipFile(msix_path) as z:
        names = z.namelist()
        nameset = set(names)
        must = ["AppxManifest.xml", "Assets/StoreLogo.png",
                "Assets/Square150x150Logo.png", "Assets/Square44x44Logo.png",
                "Assets/Square71x71Logo.png", "Assets/Square310x310Logo.png",
                "Assets/Wide310x150Logo.png",
                "Desktop-sing/Desktop-sing.exe"]
        for m in must:
            if m not in nameset:
                print("  [FAIL] 包里缺 %s" % m)
                ok = False
        if "Desktop-sing/卸载桌面歌词.bat" in nameset:
            print("  [FAIL] 商店包里不该有卸载脚本")
            ok = False
        # 商店版 STORE_MODE 下保活整体禁用，watchdog.exe 只会多一个未签名 exe 被杀软扫
        if "Desktop-sing/watchdog.exe" in nameset:
            print("  [FAIL] 商店包里不该有 watchdog.exe（见 EXCLUDE_FILES）")
            ok = False
        mf = z.read("AppxManifest.xml").decode("utf-8")
        for bad in ("{{", "}}"):
            if bad in mf:
                print("  [FAIL] 清单里有未替换的模板占位符（%s）" % bad)
                ok = False
        if "PLACEHOLDER" in mf:
            if identity_is_placeholder:
                print("  [警告] 占位标识（预期，仅供本地看结构，不能上传）")
            else:
                print("  [FAIL] 已填真实标识但清单里仍有 PLACEHOLDER 残留")
                ok = False

        # 清单里引用的每个资产都必须真的在包里（商店最常见的静态拒审原因）
        refs = set(re.findall(r'Assets\\([A-Za-z0-9._\-]+\.png)', mf))
        missing = sorted(r for r in refs if ("Assets/" + r) not in nameset)
        if missing:
            print("  [FAIL] 清单引用了但包里没有的资产：%s" % ", ".join(missing))
            ok = False
        else:
            print("  [OK] 清单引用的 %d 个资产全部就位" % len(refs))
        # 宣称支持「多档缩放」的关键资产要有 scale-400（官方建议 100/200/400）
        for base in ("Square44x44Logo", "Square150x150Logo"):
            if "Assets/%s.scale-400.png" % base not in nameset:
                print("  [FAIL] %s 缺 scale-400 变体" % base)
                ok = False
        print("  [OK] 包内 %d 个文件，%.1f MB" % (len(names), os.path.getsize(msix_path) / 1048576))
    return ok


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_wack(msix_path: str):
    if not os.path.isfile(WACK):
        print("[WACK] 本机没装 App Certification Kit，跳过（提交前建议装上跑一次）")
        return
    print("[WACK] 运行认证测试（需要管理员权限，可能要几分钟）…")
    r = subprocess.run([WACK, "test", "-apptype", "msix", "-package", msix_path],
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-1500:] if out.strip() else "[WACK] 无输出，退出码 %d" % r.returncode)


def _update_notes_zh(version: str):
    """中文「此版本中的更改」：优先 update.json（与程序内更新弹窗同源）。

    只在版本号对得上时采用，避免把上一版的日志贴到新版本（更新提交必填，
    贴错版本是常见的低级拒审理由）。
    """
    uj = os.path.join(ROOT, "update.json")
    try:
        with io.open(uj, encoding="utf-8") as f:
            data = json.load(f)
        if str(data.get("version", "")).strip() == version and data.get("notes"):
            notes = data["notes"]
            if isinstance(notes, str):
                notes = [notes]
            notes = [str(n).strip() for n in notes if str(n).strip()]
            # 「更新源说明：…」是 update.json 面向镜像机制的元信息，
            # 对商店审核员无意义，别让它混进表单。
            notes = [n for n in notes if not n.startswith("更新源说明")]
            if notes:
                return notes, "已按 update.json 同步"
    except Exception:
        pass
    return list(LISTING_WHATS_NEW["zh-CN"]), "update.json 版本未跟上，取自脚本常量"


def _terms_block() -> str:
    """四语言搜索词清单（Markdown 表格行）。"""
    rows = []
    for lg in SUPPORTED_LANGS:
        sep = "、" if lg.startswith("zh") else ", "
        rows.append("- **%s**：`%s`" % (lg, sep.join(LISTING_SEARCH_TERMS[lg])))
    return "\n".join(rows)

def _whats_new_block(version: str) -> str:
    """四语言「此版本中的更改」四块。

    注意：旧版把 update.json 的 list 直接 str() 拼进来，生成的是 Python
    列表字面量（['…', '…']），贴进表单里全是引号和方括号；这里改成
    每条一行、前缀「- 」，直接整块粘贴。
    """
    zh_notes, how = _update_notes_zh(version)
    head = ("更新提交必填，**逐语言各贴一块**（Partner Center 的语言切换在"
            " listing 编辑页左上角）。中文块（%s）：" % how)
    out = [head, "```", "\n".join("- " + n for n in zh_notes), "```"]
    for lg in SUPPORTED_LANGS[1:]:
        out += ["", "### %s" % lg, "```",
                "\n".join("- " + n for n in LISTING_WHATS_NEW[lg]), "```"]
    return "\n".join(out)

def export_listing(version: str, site_url: str = "", display_name: str = "") -> str:
    """把提审要往上贴的文案导出成一个 Markdown，免得到时手忙脚乱。

    Partner Center 各字段是分散的表单，这里按「字段名 → 内容」整理，
    复制粘贴即可。文件落在 store/out/listing-v<ver>.md。
    """
    os.makedirs(OUTDIR, exist_ok=True)
    pkgver = package_version(version)     # MSIX 文件名里是四段版本
    path = os.path.join(OUTDIR, "listing-v%s.md" % version)

    # 隐私政策 URL：站点根已知就把两个真实地址直接写出来，省得临场拼
    if site_url:
        privacy_block = (
            "- **中文 listing**（Properties → 隐私政策 URL）：`%s/privacy.html`\n"
            "- **英文 listing**：`%s/privacy.en.html`\n\n"
            "（对应仓库 `site/privacy.html` / `site/privacy.en.html`。商店策略 10.5.1 特别点名：\n"
            " Desktop Bridge 与 Win32 产品**必须**始终具备隐私政策；URL 须长期有效，\n"
            "下架前后的审核都可能来访问 —— **发布后别改这两个文件名**。）"
            % (site_url, site_url)
        )
    else:
        privacy_block = (
            "`https://<你的域名>/privacy.html`\n\n"
            "⚠️ **站点根地址还没配**：把官网地址写进 `store/identity.local.json` 的\n"
            '`"site_url": "https://xxx.netlify.app"`，再重跑 `build_store.py --listing`，\n'
            "本节会自动填成两个真实地址（中文 `/privacy.html`、英文 `/privacy.en.html`）。"
        )

    txt = f"""# 桌面歌词 微软商店提审材料（v{version}）

> 由 `store/build_store.py --listing` 自动生成，内容取自 build_store.py 的常量，
> 改文案请改常量后重新生成，别直接编辑本文件。

## 1. 程序包
`store/out/Desktop-sing-{pkgver}-x64.msix`（**未签名**，商店会重签）

> 每次提交版本号必须递增；版本号来自 `lyrics_overlay.py` 的 `APP_VERSION`，
> 会自动补成四段（{pkgver}）。

## 2. 属性 / 类别
- 产品名称：**{display_name}** —— Partner Center「管理应用名称」里**逐字符**选这一条；
  清单 `<Properties><DisplayName>` 已是同值（包名对不上预留名＝上传即拒）。注意半角 `|` 与全角 `｜` 不是同一个字符。
- 产品类别：**音乐（Music）**；次级建议：实用工具（Utilities）
- 支持设备：PC（Windows 10 1809+ / Windows 11，x64）
- 语言：**简体中文 / 繁體中文 / English / 日本語**（清单 Resources 已声明四语言；
  Partner Center「Store listing → 管理语言」添加后，各语言贴 §3 对应块）

## 3. 商品页「描述」（四语言：Store listing 添加语言后各贴一块）
### zh-CN（默认 listing）
```
{LISTING_DESCRIPTIONS["zh-CN"]}
```

### zh-TW（繁體中文 listing）
```
{LISTING_DESCRIPTIONS["zh-TW"]}
```

### en-US（English listing）
```
{LISTING_DESCRIPTIONS["en-US"]}
```

### ja-JP（日本語 listing）
```
{LISTING_DESCRIPTIONS["ja-JP"]}
```

> 每种语言的 listing 至少要填：描述 + 1 张截图（可复用同一组截图）+ 「此版本中的更改」。
> 隐私政策 URL 各语言通用同一地址。

## 4. 搜索词（每语言 ≤ 7 个；不得含价格词、不得用他人品牌名）
**同样是逐语言字段**，四个语言各贴自己那一行：

{_terms_block()}

## 5. 版本说明（「此版本中的更改」字段）
{_whats_new_block(version)}

## 6. 受限功能说明（runFullTrust）★ 必填，别贴长的
Partner Center 提示「需要请求批准才能使用受限功能 runFullTrust」，这是正常预警。
在该字段填下面这**两句话**（字段有长度限制，长文案会被静默截断）：
```
{RUNFULLTRUST_STATEMENT}
```

## 7. 认证说明（Notes for certification）
```
{CERTIFICATION_NOTES.format(version=version)}
```

## 8. 隐私政策 URL（必填）
{privacy_block}

## 9. 截图（至少 1 张；Partner Center 要求 PNG、≥1366×768、<50MB、≤10 张）
**主素材 = 播放器窗口截图**：`store/out/shots/player-*.png`，至少上传：
1. `player-1-main.png`       主播放器：最近播放、封面、歌词舞台与底部控制条
2. `player-2-report.png`     本机听歌报告
3. `player-3-history.png`    播放历史与缓存歌词
4. `player-4-immersive.png`  沉浸歌词：隐藏导航，全屏歌词舞台
5. `player-5-mini.png`       桌面歌词条（迷你模式，已合成 1600×900 展示底）

生成命令：
`.buildenv312\\Scripts\\python.exe store\\render_player_shots.py`

**补充素材**：`store/shots/real-*.png`（旧版真机浮层图，5 张 1920×1080）。
它们只能补充悬浮样式、屏保和设置面板等功能展示，**不能替代**主播放器截图；
旧图里的待机文案和浮层形态已经不能代表 2.0.8 的首屏体验。

**四语言各传一组**（Partner Center 的每个 listing 语言都有自己的截图槽位；
英文界面里配一张满屏中文的图，等于自证「没本地化」，10.7 会直接被问）：

| listing 语言 | 传哪一组 | 数量 / 尺寸 |
| --- | --- | --- |
| zh-CN | `store/out/shots/player-1…5-*.png` | 5 张 1600×900 |
| zh-TW | `store/out/shots/player-1…5-*-zh-TW.png` | 5 张 1600×900 |
| en-US | `store/out/shots/player-1…5-*-en.png` | 5 张 1600×900 |
| ja-JP | `store/out/shots/player-1…5-*-ja.png` | 5 张 1600×900 |

四组都是**离屏真实渲染**（同一套绘制代码，界面语言切过去再抓），生成命令：
`.buildenv312\\Scripts\\python.exe store\\render_player_shots.py --lang en`（换成 `ja` / `zh-TW`；不带参数即简体中文）。
`store/out/` 按 .gitignore 不进仓库，换机器要重跑；产物在提审前先看一眼，
确认界面语言确实切过去了（抓成中文说明没切成功）。

截图里只使用自写示例歌名、示例歌手和示例歌词，不嵌入真实歌曲、第三方播放器
界面或账号信息。主播放器只遥控系统 SMTC 媒体会话，不提供音乐库、推荐流或登录。

## 10. 年龄分级（IARC 问卷）
按实填写：无用户生成内容、无社交、无付费、无暴力色情内容 →
通常得到 PEGI 3 / ESRB Everyone / 中国「全年龄」。

## 11. 提交选项
建议选「认证通过后尽快发布」以便发现问题及时处理。

## 12. 提交前的自检命令
```bash
.buildenv\\Scripts\\python.exe store\\audit_round3.py     # 商店模式离线自检 + 材料完整性
.buildenv\\Scripts\\python.exe store\\build_store.py --fresh   # 全量重打包
```
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="先重跑 build_exe.py --dir")
    ap.add_argument("--name", default="", help="Partner Center 的包标识名")
    ap.add_argument("--publisher", default="", help="Partner Center 的发布者 CN=…")
    ap.add_argument("--display-name", default="",
                    help="清单里的应用名（必须是 Partner Center 预留名之一）")
    ap.add_argument("--publisher-display-name", default="",
                    help="清单里的发布者显示名（须等于 Partner Center 的 PublisherDisplayName）")
    ap.add_argument("--site-url", default="",
                    help="隐私政策页所在站点根地址（默认取 identity.local.json 的 site_url）")
    ap.add_argument("--version", default="", help="覆盖版本号（默认取 APP_VERSION）")
    ap.add_argument("--wack", action="store_true", help="打完包跑 WACK 认证")
    ap.add_argument("--listing", action="store_true",
                    help="只导出提审文案（store/out/listing-v*.md），不打 MSIX")
    args = ap.parse_args()

    if args.listing:
        listing_selfcheck()
        ver = args.version or app_version()
        p = export_listing(ver, load_site_url(args), load_display_name(args))
        print("[提审材料] %s" % p)
        return

    run_com_audit()

    sys.path.insert(0, BASE)

    src_ver = args.version or app_version()
    if src_ver != app_version():
        raise SystemExit(
            "--version %s 与 APP_VERSION %s 不一致：onedir 目录按 APP_VERSION 命名，"
            "这样出包会把错版本的产物写进新号清单。改 lyrics_overlay.py 的 "
            "APP_VERSION 后重跑，别用 --version 跨版本出包。"
            % (src_ver, app_version()))

    if args.fresh:
        print("[构建] 先跑 build_exe.py --dir …")
        # 用 3.12 构建环境：2.0.1 起运行时已迁到 .buildenv312，
        # 走老的 .buildenv 会打出 python38.dll 的包（体积与内存都回退）。
        r = subprocess.run([os.path.join(ROOT, ".buildenv312", "Scripts", "python.exe"),
                            "-u", os.path.join(ROOT, "build_exe.py"), "--dir"],
                           cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit("build_exe.py 失败（退出码 %d）" % r.returncode)

    ver = package_version(src_ver)
    name, publisher = load_identity(args)
    display_name = load_display_name(args)
    pub_display_name = load_publisher_display_name(args)
    identity_is_placeholder = "PLACEHOLDER" in (name + publisher)
    site_url = load_site_url(args)

    print("== 桌面歌词 MSIX 打包 ==")
    print("版本   : %s" % ver)
    print("标识   : %s" % name)
    print("发布者 : %s" % publisher)
    print("发布者名: %s" % pub_display_name)
    print("应用名 : %s" % display_name)
    print("隐私页 : %s" % (("%s/privacy.html" % site_url) if site_url
                           else "（未配 site_url，提审文案里会留占位地址）"))

    stage_layout(src_ver)
    write_manifest(name, publisher, ver, display_name, pub_display_name)

    os.makedirs(OUTDIR, exist_ok=True)
    msix = os.path.join(OUTDIR, "Desktop-sing-%s-x64.msix" % ver)
    if os.path.isfile(msix):
        os.remove(msix)
    if not run_makeappx(msix):
        raise SystemExit("makeappx 打包失败")
    if not verify_msix(msix, identity_is_placeholder):
        raise SystemExit("包自检未通过")

    print("\n[完成] %s" % msix)
    print("       SHA256 = %s" % sha256(msix))
    if identity_is_placeholder:
        print("       ⚠️ 当前是占位标识：上传前必须填真实 Identity（见 README-STORE.md）")
    if args.wack:
        run_wack(msix)


if __name__ == "__main__":
    main()
