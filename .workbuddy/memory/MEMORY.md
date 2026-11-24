# 桌面歌词 (Desktop-sing) 项目长期备忘（索引版）

> 细则分档：商店提审 → `MEMORY-STORE.md`；当日过程 → `YYYY-MM-DD.md`；
> 提审操作 → `store/提审上线手册.md`；商店原理/政策 → `store/README-STORE.md`。

## 命名与目录
- 英文名 `Desktop-sing`（含连字符）；显示名 `桌面歌词`；品牌串 `桌面歌词|Desktop-sing`（半角 |，与商店预留名逐字一致）。
- 数据目录 `%APPDATA%\Desktop-sing\`（日志 desktop-lyrics.log）。
- ⚠️ 工作目录 `Desktop\代码\desktop-lyrics` 不是 git 仓库；可 push 镜像在 `Documents\GitHub\Desktop-sing`，改完必须复制到镜像再 commit/push。
- 商店版装在 `WindowsApps\A135C2AE.Desktop-sing_*`（MSIX），**同一个日志文件**——诊断时先 `py-spy dump` 看进程路径确认版本，别拿日志文案猜版本。

## 分发与更新
- **GitHub** `xiaohao8/Desktop-sing`＝唯一可 push 远端 + Releases（更新主源）。
  **v2.0.4 已完整发布（2026-11-13 晚，当前线上版本）**：Release v2.0.4 三资产齐，update.json + 官网 5 处（截 v2.0.4）+ 商店包 `store/out/Desktop-sing-2.0.4.0-x64.msix`（198 文件，未签名）全部对齐，审计 **142 PASS / FAIL 0 / WARN 0**。本版是 2.0.3 的紧急修复：2.0.3 把 WASAPI 的 CoInitializeEx 混进 SMTC 采集线程，MSIX 沙箱里 try_get_media_properties_async 永久挂死（日志停在「SMTC 会话切换」，歌词彻底不获取）——2.0.4 探针独立线程化 + WinRT await 全部加超时。历史修复（SMTC 僵死桥接 / 滚轮守卫 / Tab / 偏移 ±30s）全保留。本机已装签名 localtest 2.0.4.0。蓝奏云 2.0.4 链接待上传（pending，回落 GitHub 直链）；Gitee 仍停 1.0.0。
- **官网 `https://music.202271.xyz`**（Netlify，源=`xiaohao8/music`）；隐私页 `/privacy.html`、`/privacy.en.html` 路径不能改；站点同步 `python sync_site.py --apply --push`。
- 发版必改 7 处（APP_VERSION → LANZOU_MIRRORS → update.json → 官网三卡 href → 官网版本号 → GitHub Release asset（ASCII 名）→ SHA256SUMS），**必须原子化一起上线**；发版前 grep APP_VERSION（曾退回 1.0.4）。
- ⚠️ 本机 git push 不可用（insteadOf 重写到已下线 gh-proxy）→ 用 `_gh_push.py`（REST 直推）/`_gh_release.py`。坑：只传变化 blob；别在沙箱 unlink 临时文件；REST 推后 sha 必与本地不同（远端 parent 重建），**校验用 REST 读远端文件比对关键字，别比 sha**；`.gitignore` 忽略 `.workbuddy/`。
- 图标唯一源＝根目录 `icon.png`（`site/tools/make_assets.py --only=icons` 派生）；官网 assets 引用带 `?v=<指纹>`。

## 打包与产物
- ⚠️ **2.0.1 起正式构建环境是 `.buildenv312\Scripts\python.exe`（Python 3.12），不是 `.buildenv`（3.8）**——用错会打出 `python38.dll` 包（体积/内存回退）。判据：`find dist/Desktop-sing-v<ver> -name "python*.dll"`。流程 `build_exe.py --dir` → `pkg_portable.py`（不识别 --help，跑就出活）→ nsis：`MSYS2_ARG_CONV_EXCL="*" tools/nsis/nsis-3.11/makensis.exe /DPRODUCT_VER=<ver> installer/installer.nsi`；商店包走 `store/build_store.py`（不带 --fresh 复用已验证 onedir；`--listing` 要在改完 update.json **之后**跑，否则版本说明留「请手填」）。
- `dist/release/`：安装版.exe(~26M) / 免安装极速版.zip(~34M)（3.12 线）；旧 3.8 线数字更大属回退。
- ⚠️ Defender 秒删未签名 exe：`build_store.py` 的 `stage_layout()` 必须 `_link_or_copy`（先硬链接后 copyfile），别退回 copy2；新哈希 PyInstaller exe 落盘即删（判定按哈希缓存），重建前须用户加排除。误报申诉材料在 `store/fp-submission/`。
- 验证代码进产物：`CArchiveReader(exe).toc` → extract 返回 tuple 取 [1] → marshal.loads → co_consts 与 co_names 都要搜。
- 无证书：SmartScreen 拦截属预期；`sign_release.py` 默认只校验。
- **v2.0.6 商店包已出（2026-11-14）：** store/out/Desktop-sing-2.0.6.0-x64.msix（198 文件 / 35.1 MB，未签名）+ listing-v2.0.6.md（四语言描述/搜索词/更新说明）+ 四语言截图 12 张（store/out/shots）。商店包**不得低于 2.0.6**——2.0.5 有 54 类中文残留，四语言 listing 会被 10.7 质疑。桌面渠道（GitHub/update.json/官网）仍是 2.0.5，7 处原子发版未做。
- 商店模式 STORE_MODE：更新走商店、保活禁用；提审版本号必须递增。别走自编译引导器（官方引导器备份在 `build/bootloader-src/backup-bootloader/`）。

## 联网与诊断
- 歌词直连优先（`_NET_MODE` 记出口）；本机开 **Clash TUN 模式（vgate0 网卡）时"直连"无效——所有流量仍被 TUN 接管**，Clash 重启/切节点瞬间全源「预算内无一响应」属环境抖动，30/60/90s 自动重试兜底，根治靠 Clash 规则给国内源配 DIRECT。
- ⚠️ lrclib 坑：本机到 CF 段不通（`curl 1.1.1.1/cdn-cgi/trace` vs `curl github.com` 对比定性）；有 `_lrclib_get_via_ips()` 逐 IP 兜底 + 好 IP 记忆；urllib timeout 是单次 socket 超时 → `_FETCH_LRCLIB_BUDGET=18s`（有正文只等 `_FETCH_BUDGET`）；空歌词 30/60/90s 自动重试（≤3 次），空结果不落盘。
- 源优先级固定 `order=("netease","qq","kugou")`（2026-11-11 速度基准：网易云 0.3s 全命中含逐字+翻译；QQ 欧美歌拿不到词；lrclib 13~17s）。`--hidden-import Crypto` 别删。
- **UI 全部点不动＝主线程冻结，第一件事 `py-spy dump --pid <pid>`**（pip install py-spy，Scripts 在 `.workbuddy\binaries\python\...\Scripts\`）。2026-11-11 实锤：**`is_info_line` 的标题行正则 `_SIDE` 嵌套量词 `(?:S+[ ]?){0,22}` 对超长无标点行灾难回溯（ReDoS）**，worker 霸占 GIL 主线程饿死（1.0.0 无此正则所以从没出现）——已改手写线性解析（split + 逐侧检查），`_SIDE_BAD` 必须含 `[^\S ]` 拦非空格空白（Tab 否则误删歌词行）；测试 `_test_is_info_line.py` 20 项 + `_audit_redos.py` 全量正则扫描（18 模式×9 类恶意输入）；**绝不能改回嵌套量词正则**。
- 各源延迟复测：`_diag_now_latency.py`（直连 vs 代理对比）；匹配验证必须打真实接口（`_diag_cand_match.py`）；音源 singer 字段不可单独信任（错配否决配多源一致+内容交叉验证）。
- 冻结包排障＝打探针 exe；沙箱起不来 GUI → 系统 Python 直接 import 调函数。

## 工程守则
- ⚠️ 改主文件前先 `cp x.py x.py.bak`；变异测试一次一处、锚点 0 命中要显式报错、别硬凑变异体。
- ⚠️ CRLF 文件用 Edit 会失败 → Python `io.open(newline='')`；本文件是 LF。
- ⚠️ 主路径不许有装饰性同步 IO（封面走独立 `cover_ready` 信号，守卫 `cover_pix is None` 要留）。
- ⚠️ **滚动区里的输入控件必须装滚轮守卫**（`_WheelToScroll`，2026-11-11）：QSlider/QComboBox 默认吞滚轮直接改值，用户滚动设置页会误改字体/透明度且页面滚不动。守卫把 Wheel 转给 `QScrollArea.verticalScrollBar()`；**QScrollBar 只认 angleDelta，纯 pixelDelta（触控板）必须按像素兜底补滚**，否则页面滑不动。装在 `_build()` 末尾 `findChildren` 全部控件；别把 QScrollBar 装进去（死循环），下拉弹层不受影响。测试 `_test_wheel_guard.py`（offscreen 真实 PySide6，对照组复现原 bug）+ `_audit_settings_panel.py`（构造真实面板逐个控件发滚轮，抓漏装）。
- ⚠️ `save_config` 类落盘一律原子写（tmp→fsync→os.replace）；`load_config` 损坏时留 `.corrupt` + `_salvage_json` 按行抢救。
- 坏字体喂 `QFontDatabase` 会 C++ 段错误，`_looks_like_font` 必须前置；字体供应链四件套（allowlist/哈希可选/防穿越/magic 校验）见 `FONT_HOST_ALLOWLIST`。
- `widget.grab()` 忽略可见性，断言 grab 父面板按 geometry 采样；假 watcher 的 Qt 信号必须是类属性。
- 磁盘清理不可删：`dist/release/`、`store/out/*.msix`、`store/assets/`、`icon.*`、`site/assets/`、`fonts/`、`.buildenv/`（清单见 2026-09-19 日志）。
- 回收站删除只看 `os.path.exists`，返回码不可信。
- ✅ **已修 v2.0.6（2026-11-14 真机实测发现）①打包版全局快捷键全废**：`ctypes.wintypes.MSG()` 是属性访问，PyInstaller 扫不到 → 冻结包 PYZ 里没有 `ctypes.wintypes`，热键线程建 MSG 即抛 AttributeError 退出、线程级热键被系统释放；而 `_report_hotkeys` 读的是注册阶段已写好的 `_ids`（11 项）仍弹「已启用」= 假报成功。判据：应用运行期间外部 `RegisterHotKey` 能抢注成功（err=0）= 没占用。修法已落地：`build_exe.py` 加 `--hidden-import ctypes.wintypes`，代码侧改 `from ctypes import wintypes` + 消息循环异常时清空 `_ids` 落日志（不再假报成功）；验证 PYZ 267 模块含 wintypes、打包版 4 个组合全部 1409 占用、Ctrl+Alt+T 真切换样式。**新增任何 ctypes 子模块/属性式引用后，必须复查 PYZ 模块清单**（`CArchiveReader → extract("PYZ.pyz") → ZlibArchiveReader`）。
- ✅ **已修 v2.0.6 ②英文/日文模式中文残留（原 26 处，实际共 54 类）**：`STYLE_NAMES`/`HOTKEY_DEFS` 在**模块导入时**就 `_tr()`（那时 `_UI_LANG` 恒 zh-CN），切语言只重建托盘菜单不重算表 → 永远中文；`COLOR_THEMES` 14 个配色名与 7 个位置预设是**硬编码中文字面量**从未 `_tr`。修法：`STYLE_NAMES`/`ANIM_STYLES`/`HOTKEY_DEFS`/`FONT_LIBRARY` 改存中文原文、展示处 `_tr()`（8+4 处）；`COLOR_THEMES`/`POSITION_PRESETS` 与设置面板 26 处文案补 `_tr()`；补 54 条 ×3 语言翻译（zh-TW 238 / en 233 / ja 233）。守卫测试：`_test_205_sweep.py` 新增「托盘含子菜单 0 中文」「面板 0 中文」两条。
- 真机延迟基线（v2.0.5，SMTC+QQ音乐）：中位 +0.19s / P90 +0.28s，属正常；测量法见 `_tmp_latency.py` 注释（必须像素差分+局部插值+同行去重，不能用 crc 相等或首尾线性模型）。
- ⚠️ 截图/窗口坐标工具必须 `SetProcessDPIAware()`：本机 2560×1600@125%，非感知进程只拿到 2048×1280 虚拟区域，会误判「卡片被屏幕边缘裁掉、文字被截断」。
- ⚠️ **WorkBuddy 窗口是全屏（-11,-11）→ 按屏幕坐标 `BitBlt` 只能截到 WorkBuddy 自己**。与 QQ 音乐对照必须两个窗口都用 `PrintWindow(hwnd, dc, 2 /*PW_RENDERFULLCONTENT*/)`（flag 0/1 对 QQ 桌面歌词只出纯色）。截图里一旦出现聊天文字就是遮挡没处理掉，结论作废（2026-11-15 踩过）。同框脚本 `_pair3.py`（每帧带 SMTC 基准）；独立进程读 SMTC 用 `session.get_timeline_properties()`，**不是** `playback_info.timeline_properties`（属性不存在）。抓帧/校验脚本一律用 `.buildenv312/Scripts/python.exe`（系统 python 无 PySide6）。
- ✅ **已修 v2.0.6 ③歌词永久超前几秒（2026-11-15 与 QQ 桌面歌词同框实测）**：`_apply_tick` 对「上报落后外推 1~8s」的中间地带原来什么都不做 → 一次短暂落后（换曲瞬间上报停在旧值/缓冲停顿/换快照基准）留下的超前**永不收回**，实测《这就是爱情》稳定 +4.3s，换歌才归零（这才是「有的歌同步有的歌领先几秒」的根因，不是源数据）。修法：`_DRIFT_MIN=1.0/_DRIFT_GAIN=0.35/_DRIFT_STEP=0.5` 按拍软对齐（单拍 ≤0.5s，表现为原地等，不倒着跳行；≤1s 抖动带不动）+ **上报自身回退 >2s 直接硬对齐**（换曲时 4.2→1.3，err 仅 −4.4，靠软对齐要磨 2s）。换歌分支复位 `_frozen_report/_drift_n/_bad_dur`。守卫 `_test_drift_align.py`（25 断言，AST 提取）。
- ✅ **已修 v2.0.6 ④播放器上报的总时长是脏数据**：QQ音乐 播 30 分钟的《The Campfire》时 `end_time` 只报 34.5s 而 `position` 已 413.6s → 界面 `6:53 / 0:34`、进度条永远满格、酷狗检索的 `duration` 参数被带歪。规则：**位置比 end_time 硬**，`pos > dur + 2` 就把 dur 当不可用（置 0）；落地 `_apply_tick`（显示）+ `_sane_duration(tl)`（mediaChanged 检索用）；`_time_text` 总长未知但确实在放时只显示「已播放」。守卫 `_test_time_text.py`。
- ⚠️ 校验产物内代码：主脚本以 marshal 代码对象存在 **CArchive** 里（不在 PYZ），只扫 PYZ 会全「缺失」误报；符号查 `co_names`，日志文案查 `co_consts` 字符串。
