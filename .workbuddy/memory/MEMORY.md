# 桌面歌词 (Desktop-sing) 项目长期备忘

## 命名约定
- 应用英文名：`Desktop-sing`（含连字符；原为 DesktopLyrics，2026-09-18 更名）。
- 中文显示名：桌面歌词（不变）。
- exe/进程名：Desktop-sing.exe；安装目录：D://Desktop-sing（D 盘无权限时兜底 %LOCALAPPDATA%\Desktop-sing）。
- 数据目录：%APPDATA%\Desktop-sing\（由 lyrics_overlay.py 的 APP_NAME 派生）。

## 分发渠道
- **GitHub**：https://github.com/xiaohao8/Desktop-sing —— 源码主仓 + Releases；「检查更新」主源走其 Releases API。
- **Gitee**：https://gitee.com/xiaohao3/Desktop-sing —— 国内源码镜像 + 备用更新源。
  ⚠️ 2026-09-18 时为**私有仓**：`info/refs` 返回 401（本机无法 push），访客点链接会 404；
  但 raw 文件仍可匿名取（`https://gitee.com/<r>/raw/main/update.json` 302 到带临时签名的 raw.giteeusercontent）。
  **建议转公开**——公开后 raw / Releases API / 网页浏览才都稳定。
- **蓝奏云**：国内主分发 + **程序内置更新下载镜像**（安装版 / 免安装极速版两个 zip），**链接每版都变**，见当日工作日志。
- **官网**：`site/index.html` 下载区 3 张卡（蓝奏云安装版 / 蓝奏云免安装版 / GitHub Releases）+ `dl-meta` 版本号；
  `site/assets/style.css` 的 `.dl-grid` 为 3 列（960px→2 列、720px→1 列）。
- **更新机制（2026-09-18 内置）**：更新地址留空 = 内置源。多源探测顺序＝GitHub Releases API →
  **Gitee Releases API → Gitee raw `update.json` → jsDelivr `update.json`**，取版本号最高者，任一失败不影响其它源。
  下载弹窗默认「蓝奏云下载」主按钮 + GitHub 备选。自建清单可直接带 `lanzou_setup`/`lanzou_portable` 键。
  Gitee 资源字段走 `browser_download_url` / `download_url` 兜底（不用裸 `url`，那是 API 地址）。
- **双仓库**：GitHub 是当前唯一能 push 的远端（本机只存了 GitHub 凭据）；改代码后 Gitee 需用户自行同步，
  或让用户提供 Gitee token/SSH 后由本地推送。
- **发版必改（6 处）**：`APP_VERSION` → `lyrics_overlay.py` 里 `LANZOU_MIRRORS` 加新版蓝奏云链接（不加则弹窗只剩 GitHub 渠道）→
  仓库根 `update.json`（version + 两个蓝奏云链接；jsDelivr 有 CDN 缓存）→ 官网三张卡 href → 官网版本号 →
  GitHub Release（含 asset 重传）→ 跑 `sign_release.py` 刷新 `SHA256SUMS.txt` 并随 Release 一并发布。
- **GitHub release asset 名必须用 ASCII**：中文会被服务端剥成空壳，且 PATCH 改中文名无效（返回 200 但不生效）。

## 打包与产物
- **一条龙命令**（Python 用 `.buildenv\Scripts\python.exe`，PyInstaller 6）：
  `build_exe.py --dir` → `pkg_portable.py` → `tools\nsis\nsis-3.11\Bin\makensis.exe installer\installer.nsi`。
  版本号自动取自 `APP_VERSION`。
- **dist/release 三个发布物**：`桌面歌词-v<v>-安装版.exe`（NSIS，~29MB）、
  `桌面歌词-v<v>-免安装极速版.zip`（onedir 打包，顶层目录 Desktop-sing-v<v>，~41MB）、
  `桌面歌词-v<v>-安装版.zip`（**合集**：塞上面两个文件，STORED 不压缩，~70MB，给蓝奏云当「安装版.zip」上传）。
- PyInstaller 6 的 onedir：主 exe 在 `dist\Desktop-sing-v<v>\`，依赖全在 `_internal\`。
- **⚠️ `build_store.py --fresh` 可能静默空转**（2026-09-19 实测）：它内部
  `subprocess.run(..., cwd=ROOT)` 调 `build_exe.py --dir`，**返回码 0 但产物没更新**
  （exe mtime/size 不变、字节码里还是旧串）。手动跑
  `.buildenv/Scripts/python.exe -u build_exe.py --dir`（输出重定向到文件再看）
  就正常。**判定产物真更新只看 exe 的 mtime + size**，别信 `--fresh` 的退出码。
- **验证新代码有没有真进产物**（grep 二进制没用，代码在压缩包里）：
  `CArchiveReader(exe).toc` 里主模块条目名就是脚本名 `lyrics_overlay`（type=219），
  `ca.extract('lyrics_overlay')` 返回 **tuple**（取 `got[1] if isinstance(got,tuple)`）
  → `marshal.loads` → 递归遍历即可命中。**要查两类目标**：
  ① 字符串常量搜 `co_consts`；② 函数名/全局名搜 `co_names`（`CACHE_MAX_FILES`、
  `prune_cache` 这类是名字不是字符串常量，只搜 co_consts 会误判 MISS）。
  注意：多行字符串会被编译器合并成一个常量；注释**不进** `co_consts`；
  默认替换 URL 是 `%s` 运行时拼接，字节码里只有模板串。
- **改 UI 后必须重跑 `site/tools/make_assets.py`** 刷新 `site/assets/`（官网图直接从
  `preview/*.png` 派生）。否则官网截图停留在旧 UI（2026-09-19 实测 `anim-fan.png`
  还带着早已移除的控制条，与 preview 差 11.09% 像素）。该脚本输出路径是固定的，
  重跑即可；**不能用文件 size 判断新旧**（PNG 编码差异，即使内容一致 size 也不同）。

## 代码签名与安全（2026-09-18 落地，暂无证书）
- **当前状态**：无 Authenticode 证书，产物未签名 → SmartScreen 会拦（用户需「更多信息 → 仍要运行」）。
- `sign_release.py`：默认校验（算 SHA256 并写 `dist/release/SHA256SUMS.txt` + 报每个产物签名状态），`--sign` 才真签名；
  **没配证书时整段跳过且退出码 0**，可放心挂在构建流程后面。
- 凭据走环境变量、绝不进仓库/命令行历史：`SIGN_PFX`+`SIGN_PWD` 或 `SIGN_THUMBPRINT`（+`SIGN_STORE`）；
  `SIGN_TIMESTAMP`（默认 digicert，RFC3161，证书过期后签名仍有效）/ `SIGN_DESC` / `SIGN_URL` / `SIGN_TOOL`。
  signtool 自动查找：`C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe`。
- 签名状态用 ctypes 调 `WinVerifyTrust`（不依赖 PowerShell）：**返回值要 `& 0xFFFFFFFF`**，否则 0x800B0100（未签名）
  会以负数回来被误判；zip 等非 PE 返回 0x800B0003 = 「不适用」，不是错误。
- 文档出口：README「发布与安全」+ 使用说明「安全与放行」+ 官网 dl-meta 提示行与 FAQ；用户验真 `certutil -hashfile`。
- **将来买证书**：EV 立刻建立声誉（几乎不再被拦），OV 仍需靠下载量积累；买后设好环境变量重跑 `--sign` 即可。

## 微软商店（MSIX）发布线（2026-09-18 建成，三轮复盘审计后定稿）
- **打包**：`.buildenv\Scripts\python.exe store\build_store.py --fresh` → `store\out\Desktop-sing-<v四段>-x64.msix`
  （**提审就传未签名包**，微软自己重签）。布局 = onedir 去掉卸载脚本 + Assets + 生成的清单。
- **提审材料导出**：`store\build_store.py --listing` → `store\out\listing-v*.md`
  （复制粘贴用：描述/搜索词/受限功能说明/认证说明/IARC 指引）。
- **提审前必填**：Partner Center 预留名称后，把 Package/Identity Name + Publisher 写进
  `store/identity.local.json`（**勿提交**，.gitignore 已拦）；不填 = 占位标识，只能本地看结构。
- **提审前三件人工项**：① identity.local.json 真标识；② privacy.html 发布后填 URL；
  ③ **人工截图**（仓库无现成素材，至少 1 张 1366×768+）。
- **清单模板铁律**：startupTask 扩展用**基础 desktop 命名空间**（`…/manifest/desktop/windows10`，
  不是 desktop4），否则 makeappx 报 C00CE169；模板注释会被 build_store.py 剥掉（防 `{{占位符}}` 残留）。
- **STORE_MODE 商店模式**（`is_msix_packaged()` = ctypes GetCurrentPackageFullName ≠15700）：
  更新一律走商店（check_update 短路）、自启跳 `ms-settings:startupapps`（MSIX 注册表 Run 是私有视图无效）、
  **保活禁用**（见下）、「关于」窗口按模式裁剪文案、商店版每次提审版本号必须递增。
- **资产 91 个**（100/125/150/200/400 五档倍率 + 14 档 targetsize + 深浅主题 unplated 变体 + AppList 别名）；
  清单必须声明 Wide310x150Logo 与 `uap:DefaultTile`（含 ShowNameOnTiles）；Square44/Square150 必须有 scale-400。
- **`makeappx pack` 默认就做完整语义校验**（`/nv` 才跳过）；**没有 `validate` 子命令**。
- **MSIX 三条行为限制（务必记住）**：① `C:\Program Files\WindowsApps\` 只读锁定 →
  所有写操作只能去 `%APPDATA%\Desktop-sing\`；② `%APPDATA%` 写入被虚拟化到包私有视图，
  卸载自动清理；③ **MSIX 不允许执行包内另一个 exe**（CreateProcess 返回 ERROR_ACCESS_DENIED
  且无任何日志，WindowsAppSDK #4651）→ 保活守护进程必然失败，已 `spawn_supervisor()` 短路。
- **runFullTrust**：桌面桥标配，唯一声明的能力；**`internetClient` 对 full-trust 不需要**；
  `uap10:RuntimeBehavior`/`TrustLevel` 是可选属性，MinVersion 17763 下**不必显式声明**。
  触发 Partner Center「受限功能说明」是**正常预警不是报错**，**该字段有长度限制，长文案被静默截断**（只填两句）。
- **认证是合规审查不是功能审查**（不验证功能是否正常）→ 「认证说明」写清测法极关键
  （本应用需说明「播放器要接入 SMTC 才会出歌词」，否则按 10.3 判失败）。
- **隐私政策**：商店必填 URL → `site/privacy.html`（发布后把地址填进商店表单）；内容与 `PRIVACY.md` 同源，
  两者都要如实含「歌词接口按需查询（歌名/歌手/时长/ID）+ 更新检查比对版本号」。
  政策 10.5.1 **特别点名 Desktop Bridge 与 Win32 必须始终具备隐私政策**。
- **上线自检**：`store\audit_round3.py`（强制 STORE_MODE=True 真实实例化浮层+设置面板走 refresh()，
  核对资产完整性、隐私政策与代码行为一致性）。**2026-09-19 扩展 P5 组 11 项**：
  商标禁用、本地数据控制权（缓存上限/清理入口）、功能数量口径一致、
  官网截图新鲜度、认证说明主路径。功能数量检查**从源码常量直接计数**
  （STYLE_NAMES/ANIM_STYLES/POSITION_PRESETS/saver 菜单元组），与「关于」窗口、
  商品页描述的「N 种 X」声明比对——**改功能数或改文案都会立刻 FAIL**。
  正则数 saver 元组的坑：首项 `("particle"` 会被外层 `((` 吃掉，要连同第一个
  `("` 一起收进 group 再 +1，否则永远少 1。
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
- 提审完整步骤 / 自签本地测试 / WACK / 13 条政策逐条对照 / 拒审原因表：`store/README-STORE.md`。
