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
- **官网线上地址＝`https://music.202271.xyz`**（Netlify + 自定义域名，源＝`xiaohao8/music`）。
  **这个域名就是商店必填的 `site_url`**，已写进 `store/identity.local.json`：
  中文 listing 填 `https://music.202271.xyz/privacy.html`、英文 `/privacy.en.html`
  （无扩展名的 `/privacy`、`/privacy.en` 也都能开，Netlify 的 Pretty URLs）。
  ⚠️ **`netlify.toml` 只存在于部署仓库**（`sync_site.py` 的 `LOCAL_KEEP` 会跳过它），
  改缓存/响应头要去 `Documents/GitHub/music` 改。
- **官网**：`site/index.html` 下载区 3 张卡（蓝奏云安装版 / 蓝奏云免安装版 / GitHub Releases）+ `dl-meta` 版本号；
  `site/assets/style.css` 的 `.dl-grid` 为 3 列（960px→2 列、720px→1 列）。
- **官网品牌名＝`桌面歌词|Desktop-sing`**（与商店预留名逐字一致，用户选定）：
  三页顶栏/页脚 `<span>`、`<title>`、`og:title` 全用这一个串。由 `audit_round3.py` 的
  `P5.20e`（3 项）守住 —— 改产品名时最容易漏的就是官网（图标那次就这么漏的）。
  **窄屏约定**：这串比「桌面歌词」长近一倍，`.brand` 必须 `min-width:0` + 文字
  `nowrap+ellipsis`（折行会把 56px 导航栏撑高），`≤430px` 收字号/间距；
  隐私页表格要 `.policy table{display:block;overflow-x:auto}`（否则 360px 整页横向溢出）。
- **图标只认一个源＝根目录 `icon.png`**（深色底＋青色歌词条＋`Desktop-sing` 字样）：
  主程序 `make_app_icon()`、MSIX 的 `store/make_store_assets.py`、官网的
  `site/tools/make_assets.py` **三处都从它派生**。⚠️ 官网那份原先**自己重画**了一套旧设计
  （浅蓝紫渐变＋黑音符），换品牌图后官网就成了唯一没跟上的 —— 2026-09-19 已改为同源。
  改图标只需 `python site/tools/make_assets.py --only=icons`（`--only=shots` 只刷截图，
  不带参数＝两者都刷）；**改 UI 后仍要跑一次全量**刷新截图。
- **更新机制（2026-09-18 内置）**：更新地址留空 = 内置源。多源探测顺序＝GitHub Releases API →
  **Gitee Releases API → Gitee raw `update.json` → jsDelivr `update.json`**，取版本号最高者，任一失败不影响其它源。
  下载弹窗默认「蓝奏云下载」主按钮 + GitHub 备选。自建清单可直接带 `lanzou_setup`/`lanzou_portable` 键。
  Gitee 资源字段走 `browser_download_url` / `download_url` 兜底（不用裸 `url`，那是 API 地址）。
- **双仓库**：GitHub 是当前唯一能 push 的远端（本机只存了 GitHub 凭据）；改代码后 Gitee 需用户自行同步，
  或让用户提供 Gitee token/SSH 后由本地推送。
- **发版必改（7 处）**：`APP_VERSION` → `lyrics_overlay.py` 里 `LANZOU_MIRRORS` 加新版蓝奏云链接（不加则弹窗只剩 GitHub 渠道）→
  仓库根 `update.json`（version + 两个蓝奏云链接；jsDelivr 有 CDN 缓存）→ 官网三张卡 href → 官网版本号 →
  GitHub Release（**asset 必须重传**）→ 跑 `sign_release.py` 刷新 `SHA256SUMS.txt` 并随 Release 一并发布 →
  **新 Release 的说明里要提一句 `SHA256SUMS.txt`**（不然没人知道有这个校验文件）。
- **GitHub release asset 名必须用 ASCII**：中文会被服务端剥成空壳，且 PATCH 改中文名无效（返回 200 但不生效）。
  当前三个 asset：`Desktop-sing-v<v>-setup.exe` / `Desktop-sing-v<v>-portable.zip` / `SHA256SUMS.txt`。
- **`SHA256SUMS.txt` 的规则（2026-09-19 修过 bug）**：
  ① 只收录**确实位于 `dist/release/`** 的文件 —— `sign_release.py` 会把 onedir 里的
  `dist\Desktop-sing-v<v>\Desktop-sing.exe` 也算进来，只取 basename 就会写出一行
  「用户永远找不到对应文件」的清单项（已用 `in_rel` 判定排除，但仍会在报告里打印其签名状态）；
  ② 表头（`#` 开头，`sha256sum -c` 会忽略）必须写出**ASCII asset 名 ← 本地中文名**的映射：
  发布页是 `Desktop-sing-v1.0.0-setup.exe`、本地/网盘是 `桌面歌词-v1.0.0-安装版.exe`，
  不给映射用户对不上号。映射来源是 `_ASSET_ALIASES` 常量，随版本自动填；
  ③ 重新生成是**确定性**的，内容不变就不会影响已上传文件的 digest。
- **仓库首页要有下载入口**：中英 README 都有「下载 / Download」章节，指向
  `releases/latest` 并写明两个 asset 名（版本号用 `<版本>` 占位，免得每版维护）。
  审计 `P5.18e` 守着这条 —— 改版时曾整段丢失，访客找不到安装包。
- **发布说明（release body）也是对外文档**：同样受「不该说的别说」约束，
  且**改代码后要回头核对它是否过期**（踩过：说明里还在教用户手动填更新地址，
  而程序早已内置更新源）。
- ⚠️ **本机上传 Release asset 没有 `gh` CLI**，且 Git Credential Manager 在沙箱里起不来：
  用 ctypes `CredReadW("git:https://github.com")` 读凭据 → 走 REST API
  （`DELETE /releases/assets/<id>` 再 `POST <upload_url>?name=`）。
  可复用脚本：`%TEMP%\_gh_upload.py`。

## 站点部署线（官网 + 隐私政策 → Netlify，2026-09-19 建成）
- 站点**源文件**在主仓库 `site/`；**部署副本**在独立公开仓库 https://github.com/xiaohao8/music，
  由用户自己在 Netlify 导入部署。仓库根即发布目录：`netlify.toml` 里 `publish = "."`、**无构建命令**
  （纯静态、零依赖）。刻意**不加 CSP**（页面有内联 script/style，加了会把首屏兜底逻辑拦掉）。
- 商店表单要填 `https://<站点>.netlify.app/privacy.html`（中文 listing）与 `/privacy.en.html`
  （英文 listing）；**这两个文件名/路径不能改**，改了等于让商店里的链接失效。有自定义域名优先用。
- **同步方式**：主仓库根 `sync_site.py`。默认只报告差异**不写文件**；`--apply` 才写入
  （文本按 **LF 归一化**，避免 `core.autocrlf=input` 造成的假差异）；`--check` 有漂移退出码 1；
  `--apply --push` 提交推送。部署仓库自己的 `README.md`/`netlify.toml`/`.gitignore` 在 `LOCAL_KEEP` 里，
  不参与同步、也不算「多余文件」。
- 原则：**文档点到的东西必须真实存在**。本轮就是发现「音乐站 README 承诺 `sync_site.py`」而脚本不存在、
  「主 README 文件清单列了 `site/tools/make_assets.py`」而仓库里根本没有。
- **三页已在无头 Edge 里实测过**（2026-09-19，CDP 收 Network/Log/Runtime）：
  正文 2593/1905/5409 字、CSS 生效、**0 坏图 / 0 失败请求 / 0 个 4xx / 控制台无异常**；
  首页 33 个 `.reveal` 是「进视口才点亮」（首屏读数 0 属预期，滚到底 33/33 全亮）；
  中文隐私页 8 节齐全。→ 页面本身不必再怀疑，线上只需确认地址可达。
  **坏图判据只有 `img.complete && naturalWidth===0`**；横向画廊里的 lazy 图永远 `pending`，
  只要 `broken` 为空就是正常（别写成「所有图都加载完」）。手法见技能 `headless-edge-frontend-verify`。

## ⚠️ 工作目录 ≠ 镜像仓库（踩过，务必先同步再提交）
- 真正干活/构建的是 `C:\Users\35436\Desktop\代码\desktop-lyrics`（**不是 git 仓库**，无 `.git`）；
  能 push 的是镜像 `C:\Users\35436\Documents\GitHub\Desktop-sing`。**改完必须把文件复制到镜像再 commit**，
  否则改动只活在本机、远端永远是旧的。
- 2026-09-19 实测：`store/AppxManifest.template.xml`（缺 `uap:DefaultTile` 整段）与
  `store/make_store_assets.py`（旧版）**只在工作目录修过、从未提交**；工作目录里审计全过，
  但克隆仓库照 README-STORE 打包会踩。**两边各跑一次审计**才看得出这类"只在本地修好"的假象。
- 核查手法：逐文件比工作目录 ↔ 镜像（换行归一化）＋ `git ls-files` 核对未跟踪文件。
- `store/assets/`（91 个）只有 **23 个基础图**入库，多倍率/主题变体是生成物**不入库** →
  **干净克隆里跑审计 P3.2 必然 FAIL**（属正常，先跑 `store/make_store_assets.py`）；
  `preview/` 里的 `saver_*` 诊断输出同理是可再生的，缺了不算缺陷。

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

## 磁盘清理：哪些能删、哪些绝对不能删（2026-09-19 实测，4.5 GB → 547 MB）

- **可放心删（全部可再生，合计约 3.8 GB）**：
  `store/build/layout.old-*` ×20（MSIX 打包舞台的历史副本，**注意 `store/build/layout` 是活的要留**）、
  `dist/archive/`（`*.prev.<时间戳>` 旧 onedir 副本）、`build/`（PyInstaller 工作目录）、
  `_trash_待删/`、`store/__pycache__`、`.tmp_appdata` / `_t_appdata` / `_verify_appdata`（测试残留）。
  过时的老版本：`dist/DesktopLyrics-v2.4.15*` 三件套（改名前的老一代，179 MB）。
- **绝对不能删**：`dist/release/`（**含自动更新的三个发布物 + SHA256SUMS**）、
  `store/out/Desktop-sing-1.0.0.0-x64.msix`（商店版提审包）、`store/assets/`（91 个商店图标）、
  `icon.png` / `icon.ico` / `site/assets/`（图标与官网图）、`fonts/`（内置字体，程序要用）、
  `.buildenv/`（构建环境）、`dist/Desktop-sing-v1.0.0/`（当前 onedir，重出 MSIX 与 zip 的源）。
- **★ `preview/` 里 5 张是官网图源，删了官网就再也生不出来**：
  `anim_fan_dark.png`（→ `site/assets/anim-fan.png`，**且被自检 P5.9 拿来比对新鲜度**）、
  `controls.png`、`menu.png`、`settings_panel.png`（→ `panel.png`）、
  `style_glass_dark.png`（→ `hero.png`）。其余 39 张是诊断渲染图，可用 `preview_render.py` 再生。
- **程序运行时的数据不必动**：`%APPDATA%\Desktop-sing` 只有约 305 KB，
  歌词缓存才 10 个文件（且有 `CACHE_MAX_FILES=3000` / 40MB 上限自动淘汰）；
  要清就用设置面板里的「歌词缓存」入口，别手工删。
- **回收站删除的坑**（复用脚本 `C:\Users\35436\AppData\Local\Temp\_recycle_batched.py`）：
  `SHFileOperationW` 对大目录**只删一部分就返回**（ret=120/124），要**循环重试到 exists 为假**；
  小对象可能 ret=2 但**其实已删**。👉 **返回码不可信，只看 `os.path.exists`。**
  同时传父+子目录会行为异常，要先剔除嵌套；3.8 GB 约 3 分半，必须后台跑。
- 流程上：这是个人目录（`Desktop\代码\`）→ **先只读盘点出清单，让用户圈定范围后再动手**，走回收站。

## 微软商店（MSIX）发布线（2026-09-18 建成，三轮复盘审计后定稿）
- **打包**：`.buildenv\Scripts\python.exe store\build_store.py --fresh` → `store\out\Desktop-sing-<v四段>-x64.msix`
  （**提审就传未签名包**，微软自己重签）。布局 = onedir 去掉卸载脚本 + Assets + 生成的清单。
- **提审材料导出**：`store\build_store.py --listing` → `store\out\listing-v*.md`
  （复制粘贴用：描述/搜索词/受限功能说明/认证说明/IARC 指引）。
- **提审前必填**：Partner Center 预留名称后，把 Package/Identity Name + Publisher（+ 预留的
  `display_name`、站点 `site_url`）写进 `store/identity.local.json`（**勿提交**，.gitignore 已拦）；
  不填 = 占位标识，只能本地看结构。
- **提审前三件人工项**：① identity.local.json 真标识 + 预留名；② privacy.html 发布后填 URL；
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
- **隐私政策**：商店必填 URL → 站点根 + `/privacy.html`（中文 listing）与 `/privacy.en.html`（英文）；
  内容与 `PRIVACY.md` 同源，两者都要如实含「歌词接口按需查询（歌名/歌手/时长/ID）+ 更新检查比对版本号」。
  政策 10.5.1 **特别点名 Desktop Bridge 与 Win32 必须始终具备隐私政策**。
- **`store/identity.local.json`（本机、勿提交）六个键**：`name`（Partner Center 的
  Package/Identity/Name）、`publisher`（`CN=…` 主题串，**必须原样复制逐字符匹配**）、
  **`publisher_display_name`**（Package/Properties/PublisherDisplayName，个人账号＝**真实姓名**，
  填成产品名会报「清单中的 PublisherDisplayName 元素…与发布者显示名称不匹配」）、
  `display_name`（**预留的应用名，必须逐字符等于 Partner Center「管理应用名称」里的一条**，
  默认 `桌面歌词|Desktop-sing`）、`site_url`（站点根）、
  **`package_family_name`**（PFN，仅用于自检反推校验 publisher 哈希，见下）。
  `site_url` 填了之后出包会打印隐私页地址，
  `build_store.py --listing` 会把中英两个真实地址 + 产品名称直接写进提审文案。
  也可用 `--name / --publisher / --publisher-display-name / --display-name / --site-url` 临时覆盖。
  不填只能出**占位标识包**（包内 `Identity Name="Desktop-sing-PLACEHOLDER"`），**不能上传**。
  ⚠️ **半角 `|`(U+007C) 与全角 `｜`(U+FF5C) 不同字符**；清单 DisplayName 对不上预留名会被拒
  （*name found in the package is not one of your reserved app names*）。实测 `|` 能过 `makeappx`。
  **2026-09-19 已填真实值**：`A135C2AE.Desktop-sing` / `CN=815AB3D3-C7A7-40CB-93F0-57D02D5FAAF0` /
  `付志豪` / `桌面歌词|Desktop-sing` / `…_8ahsnwh40hshg`，
  **`store/out/Desktop-sing-1.0.0.0-x64.msix` 已是可上传的正式包**
  （SHA256 `b5136c0f…`，234 文件 / 43.7 MB，包内三项与 Partner Center 逐字符一致、无 `{{ }}` 残留）。
- **PFN 反推 = 免费的自证「Publisher 没抄错」**（`audit_round3.py` 的 P5.20c3）：
  `PFN = <IdentityName>_<hash13>`，`hash13 = base32_13( sha256(publisher.encode("utf-16-le"))[:8] << 1 )`，
  字母表 `0123456789abcdefghjkmnpqrstvwxyz`。**`<< 1` 不能省**（64→65 bit，末位补 0），
  少了最后一字符必错（踩过：算 `…hshh`、实际 `…hshg`）。抄错一个字符 → 哈希完全不同。
- **本地实测（想看商店版真实效果）：`store/make_localtest.py`** —— 一条命令自签一份副本
  给你装；证书 Subject = 清单 Publisher，PFN 与正式包相同故真进 STORE_MODE。
  ⚠️ **证书必须进机器级证书库（需管理员），用户级无效**（实测 `0x800B0109`）；
  ⚠️ **测完必须卸载**（与正式版同 PFN）。详见 `MEMORY-STORE.md`。
  ⚠️ 看不到歌词的头号原因不是 bug —— 要靠 SMTC，**没播放器在播就只有托盘图标**。
- **上线自检**：`store\audit_round3.py`（强制 STORE_MODE=True 真实实例化浮层+设置面板走 refresh()，
  核对资产完整性、隐私政策与代码行为一致性）。**2026-09-19 共 129 项**；通过判据＝
  **FAIL 0，且上传前 WARN 也要 0**（当前已是 0/0）。
  原有 P5 组：商标禁用、本地数据控制权（缓存上限/清理入口）、功能数量口径一致、
  官网截图新鲜度、认证说明主路径。**P5.18 发布物料自洽 6 项**（校验清单每行指向真实文件、
  只收录 `dist/release/`、ASCII asset 名映射、中英 README 有下载指引）；
  **P5.19 站点部署副本一致性 5 项**（与 `site/` 归一化后逐字节一致、
  `netlify.toml` 无构建命令且发布目录为仓库根、三张页面都在根目录、`sync_site.py` 存在）。
  **P5.20 提审前置 14 项**：`P5.20a/a2` 本地标识与发布者显示名是否填全（缺则 WARN）、
  `P5.20b` 站点地址；**`P5.20c` 直接读 `out/` 最新 .msix 的清单与本地标识比"档位"** —— 填了标识
  却没重出包就 FAIL（守住「上传占位包」这个最致命的低级错误）；
  **`P5.20c2` 包内 Name/Publisher/PublisherDisplayName 与本地逐字段比对**（抄错即 FAIL）；
  **`P5.20c3` PFN 反推**（见上）；**`P5.20c4` `store/out/` 根目录只许有一个 `.msix`** ——
  自签测试包 `dev-signed.msix`（标识 `Desktop-sing-PLACEHOLDER`，**上传必被拒**）
  与历史版本一律放 `store/out/dev/`（`*.msix` 这个 glob 不递归，不会误报）；
  **`P5.20d` 两项盯应用名** —— 清单 DisplayName
  必须与本地配置一致，**改了名没重出包也 FAIL**（守住「包名对不上预留名」）；
  **`P5.20e` 三项盯官网品牌名** —— 三页的品牌标记必须 == 产品名、`<title>` 须含产品名
  （`<title>` 判「包含」不判「开头」：隐私页是「隐私政策 · 产品名」）；
  **`P5.21` 三项盯资源版本戳与分享卡片** —— 页面里所有 `assets/` 引用必须带 `?v=<内容指纹>`，
  指纹要与 `site/assets/` 实际内容对得上（否则「改了资产没重跑 make_assets.py」），
  另 **`og:image`/`og:url` 必须是绝对地址**（社交抓取器不解析相对路径，写相对路径分享卡片
  就退化成纯文字 —— 2026-09-19 已修）。
  ⚠️ **这是换品牌图后「线上还是旧图标」的真凶**：部署侧 `netlify.toml` 给 `/assets/*`
  设了 7 天强缓存，原本的理由是「文件名带内容含义，换图就换文件」——但图标文件名是
  **固定**的，前提根本不成立。现在 URL 带内容指纹，前提才真成立。
  改 assets 后**必须重跑 `site/tools/make_assets.py`**（会自动重打指纹）。
  **复用产物快招**：`build_store.py` **不带 `--fresh`** 会复用 `dist/Desktop-sing-v<v>` 只重铺
  layout + makeappx（秒级），改 UI/名字后想快速重出包验证就用它，别每次都重跑 PyInstaller。
  功能数量检查**从源码常量直接计数**
  （STYLE_NAMES/ANIM_STYLES/POSITION_PRESETS/saver 菜单元组），与「关于」窗口、
  商品页描述的「N 种 X」声明比对——**改功能数或改文案都会立刻 FAIL**。
  正则数 saver 元组的坑：首项 `("particle"` 会被外层 `((` 吃掉，要连同第一个
  `("` 一起收进 group 再 +1，否则永远少 1。
→ **审核红线 / 许可合规 / 多显示器 / 卸载残留 / 沙箱坑：见 `MEMORY-STORE.md`**
- 提审完整步骤 / 自签本地测试 / WACK / 13 条政策逐条对照 / 拒审原因表：`store/README-STORE.md`。
