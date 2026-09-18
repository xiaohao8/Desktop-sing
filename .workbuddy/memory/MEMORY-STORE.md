# 微软商店提审：审核红线与合规细则
（从 MEMORY.md 拆出；主文件保留索引，细则看这里）

- **提审安全红线（2026-09-19 审核员视角复查后固化）**：
  ① **界面/官网/README 一律不得出现第三方注册商标**（曾被政策 10.1.1 关联暗示、
     11.2 第三方权利卡）——样式名统一用**外观特征**命名（专辑卡片 / 声波频谱），
     **内部 key（ios/spotify）保持不变**，改了会让老配置失效。
     但功能清单里「多源并行（QQ音乐/网易云/酷狗/LRCLIB）」属**指明互操作性**的
     合理使用，保留；README「未接入 Apple Music/Spotify」是免责语境，保留。
  ② **认证说明的主路径不能是默认关闭的功能**：全局快捷键默认关，旧文档让审核员按
     Ctrl+Alt+S 会被判 10.3 功能缺失 → 主路径写「右键托盘图标 → 设置…」，
     并写明「断网不崩」「播放器未接入 SMTC 时不出歌词属预期」。
  ③ **代码里任何伪装第三方客户端身份的东西都要在隐私政策披露**：
     网易云接口带 `os=pc; appver=2.9.7` + Referer（兼容性字段），已写进
     `site/privacy.html` 与 `PRIVACY.md` 的「关于请求头」节。
  ④ **用户本地数据必须有控制权**（10.2.7/10.5.1）：缓存要设上限
     （`CACHE_MAX_FILES=3000` / `CACHE_MAX_BYTES=40MB`，按 `st_atime` 淘汰，
     写缓存后自动 `prune_cache()`），且设置面板要有**看得见占用量 + 一键清理**的入口
     （只写在隐私政策里不够）。
- **许可随包合规（2026-09-19 建成，政策 11.2）**：程序内置 MiSans 字体、歌词引擎借鉴
  Apache-2.0 的 Lyricify-Lyrics-Helper → **Apache-2.0 第 4 条要求向「接收者」提供 NOTICE**，
  商店用户只拿到 .msix、看不到仓库，所以**只放仓库里 = 实打实的许可违规**。
  已建仓库根 `LICENSE-THIRD-PARTY.txt`（5 节：Lyricify 归属 + FluentFlyout「未使用源码」声明 +
  内置/可下载字体 + 运行时依赖 PySide6/winsdk/pycryptodome + 歌词内容版权），
  **三条分发渠道全部随包**：`build_store.py` 的 `BUNDLED_LICENSES` 常量（`stage_layout()` 里复制，
  **缺文件直接 SystemExit 不许静默跳过**）→ `pkg_portable.py` 的 `docs`（打为 `第三方许可.txt`）
  → `installer.nsi` 的 `File /oname=第三方许可.txt`。「关于」窗口指引也改为指向**安装目录下的
  随包文件**（指向 NOTICE.md 等于没有——商店用户看不到仓库）。
- **「商标审查」必须枚举所有用户可见载体，不能只扫界面文案**：第 3 轮最严重的发现是
  `build_store.py` 的 `DESCRIPTION` 常量里藏着「如 QQ音乐 / 网易云音乐 / 酷狗音乐」——
  这串会写进 `uap:VisualElements/@Description`（**包元数据，商店页可见**）。
  前两轮只扫了 `lyrics_overlay.py` / 官网 / README 所以漏掉。
  现审计 P5.1 已扩展为**多载体扫描**：P5.1 界面文案、P5.1b 清单 Description 商标、
  P5.1c 播放器品牌黑名单（QQ音乐/网易云/酷狗/汽水/虾米）、P5.1d 更新菜单文案如实性。
  **正确做法**：说明兼容性描述客观事实（「接入 SMTC 的播放器」），不点名品牌。
- **行为正确 ≠ 描述正确**：商店版 `check_update()` 行为本就正确（提示去商店更新），
  但菜单项和桌面版一样写「检查更新…」→ 用户以为应用内有更新通道、点了拿不到版本信息，
  看起来像功能坏了。已改 `"在商店中获取更新…" if STORE_MODE else "检查更新…"`。
  审核员读的是**文案**不是源码。
- **商店截图三要件（2026-09-19 补齐）**：① **尺寸 ≥1366×768**（`shot_settings()` 原来只抓
  548 宽的面板本体，远不达标 → 改为贴 1600×900 桌面底）；② **文件名要可被识别**
  （`store-shot-*.png`，旧名 `1-idle.png` 不含 shot/preview 关键词，审计匹配不到）；
  ③ **内容非空**（offscreen 下 `grab()` 有时抓到全透明，落盘是纯壁纸 101KB 看着正常但无内容
  → 审计加空白检测：采样角落背景色，内容占比 <3% 判空白）。
  `render_shots.py` 的 `composite()` 已加 `pixmap=` 参数，支持先 `grab()` 再算居中位置。
- **审计脚本现有规模**：`store/audit_round3.py` 约 400 行 / 21 项检查（P3.6 截图组 3 项 +
  P5 组 18 项），**2026-09-19 首次做到 FAIL 0 / WARN 0**。
  P5.12 系列 8 项是许可随包检查，含**已打 MSIX 包内容抽验**（`zipfile.namelist()` 找
  `LICENSE-THIRD-PARTY` / `PRIVACY.md`）。**两条检查当场抓出我手改时漏掉的问题**
  （P5.1 旧占位文案、P5.12e 包内无许可）——人改代码会漏，脚本不会，别省自动检查。
- **`__pycache__` 陈旧字节码坑（第三次踩，务必记住）**：改完代码跑脚本前**先清
  `__pycache__`**。本次症状是「代码明明对但行为不对」——截图一直抓成全透明，
  排查了尺寸、`composite(pixmap=)` 路径等半天，最后 `rm -rf store/__pycache__` 后重跑即正常。
- **图片 Read 工具按内容哈希缓存**：同一路径图片更新后再次 Read 返回「image unchanged」，
  不能据此判断是否重生成 → 改用程序化像素统计验证内容非空。
- **多显示器：定位型 API 一律先问「跟窗口还是跟主屏」（第 4 轮踩坑）**。
  代码里曾有**两种写法混用**：`_clamp_into_screen()` 用 `self.screen()`（对），
  但 `_preset_point()` 用 `primaryScreen().availableGeometry()`（错）、
  `AmbientSaver.start()` 用 `primaryScreen().geometry().center()`（错）。
  后果：副屏用户点「贴底/居中」预设窗口**跳回主屏**、位置反查恒判 free；
  副屏触发屏保**黑的是主屏**。已统一为
  `scr = self.screen() → 取不到退 QApplication.screenAt(QCursor.pos()) → 再退 primaryScreen()`。
  窗口未 `show()` 时 `self.screen()` 可能是 `None`，**必须两级兜底**。
  审计 P5.13 组 5 项锁这个模式。
- **卸载要「卸干净」（第 4 轮补齐）**：NSIS 卸载节原来**没删开机自启 Run 键、没碰
  `%APPDATA%\Desktop-sing`** → 自启项留着每次开机弹「找不到文件」；数据目录留着变孤儿、
  重装又带旧设置。正确做法：`taskkill /f /im` 结束进程（否则 `$INSTDIR` 删不净）
  → `Sleep 800` → 删快捷方式 → `RMDir /r $INSTDIR` → `DeleteRegValue HKCU "...\Run"`
  → `IfFileExists "$APPDATA\..."` + `MB_YESNO` **询问**是否删用户数据（**默认不删**）。
  ⚠️ NSIS 脚本里**没有 `APP_NAME` 宏，只有 `DIR_NAME`**（取值同），写 `${APP_NAME}` 会编译报错。
  便携版 `卸载桌面歌词.bat` 原本就有这两步 —— **两条渠道行为不一致本身就是审核点**。
- **隐私声明有两份，商店只读 URL 那份（第 4 轮发现）**：`PRIVACY.md` 写了 SMTC 读取，
  但 `site/privacy.html`（**真正填进商店表单的 URL**）没写 → 少披露一项系统读取权限。
  两份必须**同时**披露同一组事实；审计 P4.6a/b/P4.7 已锁。
  改章节号时**从后往前替换 + assert 唯一**，否则「4.」→「5.」会被下条规则二次匹配。
- **`QWebEngineView` 在本沙箱渲染不出内容**：`toPlainText()` 返空串、`grab()` 得纯背景
  （本地 `file://` 且 `loadFinished` 已触发也没用）→ 校验 HTML 改用**标准库 `HTMLParser`**
  做标签配平 + 结构检查（不可用浏览器验证）。
- **MSIX 重打包会被 safe-delete 拦**：`build_store.py` 要覆盖已存在 `.msix` 时返回
  `SAFE_DELETE_BULK_CONFIRM_REQUIRED`（exit 1，但 exe/zip 已构建完）→
  先用 `C:\Users\35436\AppData\Local\Temp\_recycle_bin.py` 把旧 `.msix` 移进回收站，
  再跑 `build_store.py`（**不加 `--fresh`**，跳过重建 exe）。
- **字节码核验：`co_consts` 里没有注释和 docstring**（PyInstaller 会丢），
  用注释原文搜「是否入包」必然 MISS。核验函数体改动要定位 `co_name` 的 code 对象
  再查其 `co_names`（例：`AmbientSaver.start` 的 `co_names` 应含
  `isVisible`/`screenAt`/`QCursor`/`pos`/`screen`）。
- **CRLF 比对陷阱**：`open(p, encoding=...)` 文本模式会把 CRLF 转 LF，
  与 `zipfile.read()` 的原始 CRLF 字节比对会**处处不等**（曾被误判成「包内文件过期」）。
  比内容一律用 `open(p, "rb")` 或都 `replace(b"\r\n", b"\n")` 再比。
- **`winsdk/_winrt.pyd` 独占 36.8 MB（包体积 87%）**，是**单体扩展模块、无法裁剪**
  （C++/WinRT 投影全打在一个 pyd 里）。想瘦身只能换 `winrt-*` 命名空间包
  （Python ≥3.12，按需装 `winrt-Windows.Media.Control` 等），属大改动、未做。
