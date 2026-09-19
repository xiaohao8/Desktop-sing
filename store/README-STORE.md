# Microsoft Store（MSIX）发布指南

`store/` 目录专门负责微软商店发布线，与 GitHub/蓝奏云的分发渠道完全独立。

> **只想照着做一遍？** 看 **`store/提审上线手册.md`** —— 那是从零到上架的线性操作清单
> （准备 → 出包 → 验收 → 逐字段提交 → 发布后）。本文件是**参考手册**，讲「为什么」：
> 商店版行为差异、政策逐条对照、拒审原因、踩坑记录。

```
store/
├── 提审上线手册.md              ★ 按顺序照着做的操作手册（准备 + 步骤）
├── AppxManifest.template.xml   清单模板（占位符由构建时替换，不要直接改它发布）
├── make_store_assets.py        生成全部商店图标资产（91 个，已跑通）
├── render_shots.py             离屏生成商店截图素材（3 张 1600×900）
├── build_store.py              一键打包 / 导出提审材料
├── audit_round3.py             商店模式离线自检（政策合规 + 运行时行为 + 材料完整性）
├── assets/                     生成的图标资产（提交仓库，免得每次重渲染）
├── identity.local.json         ★ 包标识 + 应用名 + 隐私政策站点地址（本机填一次，勿提交、勿外传）
├── build/layout/               打包工作目录（可随时删）
└── out/
    ├── Desktop-sing-x.y.z.w-x64.msix    最终产物（未签名）
    ├── listing-v<x.y.z>.md             提审材料（复制粘贴用）
    └── shots/                          商店截图素材（不进仓库）
```

## 0. 为什么商店版行为不一样

| 行为 | 普通版 | 商店版（MSIX） |
|---|---|---|
| 更新 | GitHub/Gitee 查版本 + 蓝奏云下载 | **一律走商店**（`STORE_MODE` 已内置短路） |
| 开机自启 | 注册表 HKCU Run | **startupTask 扩展** + 系统「启动」设置页 |
| 进程保活 | 守护进程拉起 | **禁用**（见下，MSIX 不允许） |
| 卸载 | 自带卸载脚本 | 系统设置 → 应用（商店包不进包卸载脚本） |
| 设置面板「更新」区 | 更新地址 / 自动检查 / 立即检查 | 一段「更新由商店分发」的说明文字 |
| 托盘「系统」菜单 | 开机自启（勾选）/ 进程保活（勾选） | 开机自启（跳转到系统设置）/ 保活项**隐藏** |
| 「关于」窗口 | 含「进程保活」字样 | 不含（避免虚报能力） |

代码里 `lyrics_overlay.py` 的 `is_msix_packaged()` 用
`kernel32.GetCurrentPackageFullName` 判断运行环境（非打包环境返回 15700），
打包后自动切到商店行为，**同一份代码同时出两种产物**。

### 三条 MSIX 行为须知（踩过坑，务必记住）

1. **安装目录只读且被锁定**：`C:\Program Files\WindowsApps\` 不可写。
   本程序所有写操作都在 `%APPDATA%\Desktop-sing\`，**没有一处写安装目录**（已审计确认）。
2. **`%APPDATA%` 写入被虚拟化**到「包私有视图」（per-user per-app），
   卸载应用时系统会自动清理这部分数据。所以隐私政策里承诺的「卸载即清除」是成立的。
3. **注册表写入也重定向到私有视图**：这就是为什么商店版不能靠 HKCU\...\Run 自启
   ——系统开机时根本看不到这条记录，必须用 `startupTask` 扩展。

## 1. 前置条件（一次性）

1. **Partner Center 开发者账号**：<https://partner.microsoft.com/dashboard>
   个人账号一次性注册费（约 $19 / 等值人民币，以官网为准），公司账号更贵。
2. **预留应用名称**：Partner Center → 新建应用 → 填名称「桌面歌词」。
   若被占用可试「桌面歌词 Desktop-sing」等变体——名称必须与清单里的
   `DisplayName` 一致，否则提审会被打回。
3. **拿到包标识**：应用 → 产品管理 → 产品标识，复制两样：
   - **包名**（Package/Identity/Name，形如 `12345Desktop-sing`）
   - **发布者**（Publisher，形如 `CN=1A2B3C4D-…`）

   ⚠️ **必须从 Partner Center 原样复制，别手敲**——Publisher 是微软签发证书的
   主题串，逐字符匹配，写错包根本装不上。

4. 写入本机标识文件 `store/identity.local.json`（**勿提交**）：

   ```json
   {
     "name": "12345Desktop-sing",
     "publisher": "CN=1A2B3C4D-5E6F-...",
     "display_name": "桌面歌词|Desktop-sing",
     "site_url": "https://xxx.netlify.app"
   }
   ```

   不填也能出包（占位标识），但**只能本地看结构，不能上传**。

   **`display_name` 必须逐字符等于 Partner Center 里预留过的名字之一**（「管理应用名称」
   页面），否则上传直接被拒：*The name found in the package is not one of your reserved
   app names*。清单 `<Properties><DisplayName>` 与 `<Application>` 的 DisplayName 都由它填充
   （默认值已是 `桌面歌词|Desktop-sing`，改名后才需覆盖）。⚠️ 半角 `|`(U+007C) 与全角
   `｜`(U+FF5C) 是两个字符，抄的时候务必照抄页面上的那个。

   `site_url` 是隐私政策页所在的站点根（§1.4 部署后拿到）：填了之后出包会打印
   `隐私页 : …/privacy.html`，`build_store.py --listing` 也会把中英两个真实地址
   直接写进提审文案。四项都可用 `--name` / `--publisher` / `--display-name` /
   `--site-url` 临时覆盖。

   出包脚本与自检都会盯着这件事：`audit_round3.py` 的 `P5.20a/b` 在没填时给 WARN，
   **填了标识却没重出包**由 `P5.20c` FAIL，**改了应用名却没重出包**由 `P5.20d` FAIL，
   **官网品牌名对不上产品名**由 `P5.20e` FAIL
   （都是「三处名字/图标各说各话」的现场）。

## 2. 打包

```bash
# 用现有 dist/ 产物打包
.buildenv\Scripts\python.exe store\build_store.py

# 从源码全量重建再打包（提审前用这个，保证产物=当前代码）
.buildenv\Scripts\python.exe store\build_store.py --fresh

# 只导出提审材料 Markdown
.buildenv\Scripts\python.exe store\build_store.py --listing
```

产物：`store/out/Desktop-sing-1.0.0.0-x64.msix`（未签名——**商店提审就传未签名包**，
微软会用它自己的证书重签）。

脚本自检项：包内必备文件（清单 + 六类图标 + exe）、**清单引用的每个资产都必须在包里**、
无卸载脚本残留、清单无未替换占位符、版本四段数字、`Square44x44Logo` / `Square150x150Logo`
必须有 `.scale-400.png` 高倍率变体。

> `makeappx pack` **默认就做完整语义校验**（清单 schema + 文件存在性），
> 不要加 `/nv`。没有 `makeappx validate` 这个子命令。

## 3. 本地安装测试（自签名）

未签名的 MSIX 装不上，本地测试需要自签证书：

```powershell
# ① 建自签证书（Subject 必须与清单 Publisher 逐字符一致！）
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=1A2B3C4D-5E6F-..." `
  -KeyUsage DigitalSignature -FriendlyName "Desktop-sing 本地测试" `
  -CertStoreLocation "Cert:\CurrentUser\My" -TextExtension @(
    "2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")

# ② 用它签 MSIX（证书在「用户级」存储时不要加 /sm，那是机器级）
signtool sign /fd SHA256 /sha1 <证书指纹> store\out\Desktop-sing-1.0.0.0-x64.msix

# ③ 信任该证书（仅本机测试用，需管理员）
Export-Certificate -Cert $cert -FilePath test.cer
Import-Certificate -FilePath test.cer -CertStoreLocation "Cert:\LocalMachine\TrustedPeople"

# ④ 安装
Add-AppxPackage -Path store\out\Desktop-sing-1.0.0.0-x64.msix
```

装上后重点验证：
- 托盘菜单「开机自启（系统设置）」能否跳转 `ms-settings:startupapps`；
- 设置面板：系统卡片是「打开启动设置」按钮、更新区是商店提示（无更新地址输入框）、
  **无「进程保活」开关**；
- 「检查更新…」菜单提示走商店；
- 「关于」窗口里没有「进程保活」字样；
- 歌词、屏保、快捷键等主功能与普通版一致。

## 4. WACK 认证（建议提审前跑）

```bash
.buildenv\Scripts\python.exe store\build_store.py --wack   # 需管理员权限
```

WACK（Windows App Certification Kit，`appcert.exe`）就是商店审核用的测试集，
本地过了基本就不会栽在技术认证上。**它需要管理员权限**；
非管理员环境下会 `Permission denied`，属预期，不是代码问题。

## 5. 提审材料清单（Partner Center 页面填写）

> 全部文案已由 `build_store.py --listing` 导出到 `store/out/listing-v<x.y.z>.md`，
> 直接复制粘贴即可。下表是索引。

| 材料 | 内容 | 备注 |
|---|---|---|
| 包 | 上传 out/*.msix | 未签名；**每次提交版本号必须递增** |
| 名称 | 桌面歌词 | 与清单 DisplayName 一致 |
| 描述 | 见 `STORE_LISTING_DESCRIPTION` | **必须写清重要限制**（见 §7） |
| 搜索词 | ≤ 7 个 | 不得含价格词、不得用他人品牌名 |
| 截图 | 至少 1 张；现成 **3 张 1600×900** 在 `store/out/shots/` | 由 `store\render_shots.py` 离屏生成，**不是真机截屏**：建议另补 1 张真机桌面图。`store/out/` 不进仓库，需重跑脚本 |
| 图标 | 商店 listing 图标 | 300×300 PNG，可复用 assets 里的方形图 |
| 类别 | 音乐 / Music（次级：实用工具） | |
| 年龄分级 | 完成 IARC 问卷 | 无用户内容、无社交 → 通常全年龄 |
| **隐私政策 URL** | **中文 listing** 填 `site_url` + `/privacy.html`；**英文 listing** 填 `site_url` + `/privacy.en.html` | **必填**，缺失直接拒审。商店是全球分发的，英文页区只填中文隐私页等于英文用户读不到声明。站点部署在独立仓库 `xiaohao8/music`（Netlify），改完站点记得 `python sync_site.py --apply --push` |
| **随包文档语言** | 中英各一份（`使用说明.txt`/`USAGE.en.txt`、`PRIVACY.md`/`PRIVACY.en.md`） | 两条渠道同一套清单，`P5.12h` 会逐渠道校验 |
| **受限功能说明** | `RUNFULLTRUST_STATEMENT` | **必填**，只填两句，见 §6 |
| 认证说明 | `CERTIFICATION_NOTES` | 帮审核员知道怎么测，见 §6 |
| 联系信息 | 邮箱 / 网站 | 审核沟通用 |

## 6. runFullTrust 与认证说明（重点，别踩坑）

打包桌面应用声明 `rescap:Capability Name="runFullTrust"` 是**标配且必须**，
但上传包后 Partner Center 会提示：

> 你需要先请求批准，才能在你的应用中使用以下受限功能：runFullTrust

**这是正常预警，不是报错**，不需要提前单独申请，也不会阻碍提交
（所有 Tauri / Electron / Win32 转 MSIX 的桌面应用都会触发）。
在「提交选项 → 受限功能说明」里填理由即可。

**⚠️ 该字段有长度限制，长文案会被静默截断**，所以 `RUNFULLTRUST_STATEMENT`
只写了两句话：说明是 Win32 桌面程序、需要 SMTC 读取与透明无边框窗口绘制，
不修改系统文件、不装其他软件、数据仅存本机。

另外，**`internetClient` 对 full-trust（mediumIL）打包应用是不需要的**
——网络访问对桌面应用默认可用；`internetClient` 是 UWP appContainer 应用才要的。
本清单**只声明 `runFullTrust`** 一个能力，干净且不会被质疑多要权限。

**认证的实质是合规审查，不是功能审查**：审核只验证签名、清单合法性、能力声明、
政策合规、启动不崩溃；**不会去验证每项功能是否真的正常**。所以
「认证说明」里写清怎么测非常关键——审核员卡住时会按 10.3「产品可测试」判失败。

## 7. 商店政策的硬约束（已逐条核对 7.20 版）

| 条款 | 要求 | 本项目的落实 |
|---|---|---|
| **10.1.1** | 元数据必须准确描述功能、特性、体验和**任何重要限制**（含输入设备） | 描述里明确写了：仅 Win10 1809+/Win11 x64、播放器必须接入 SMTC、需联网、界面仅简体中文。**界面里的「关于」窗口也按商店模式调整，不再宣称「进程保活」** |
| **10.1.3** | 搜索词 ≤ 7 个唯一术语，不含价格词，不用他人产品标题 | 已给出 7 个词，全部是功能描述词 |
| **10.1.4** | 首次运行体验须清晰体现价值主张 | 启动即显示歌词浮层，无向导、无登录 |
| **10.2.5** | 通过 Store 分发的产品其安装与更新只能用 Store | 商店版 `check_update` 短路、设置面板不提供更新入口，**无任何自更新通道** |
| **10.2.7** | 必须清楚告知并让用户能彻底卸载 | 商店应用经系统设置卸载，`%APPDATA%` 私有视图由系统一并清理；包内**不含**自定义卸载器（会被质疑） |
| **10.2.8** | 改 Windows 设置须用受支持方法且获用户同意 | 自启用官方 `startupTask` 扩展（默认 `Enabled="false"`）；置顶/点击穿透用 Qt 官方窗口标志；**未使用任何无障碍 API** |
| **10.3** | 必须可测试 | 无账号无登录；已备 `CERTIFICATION_NOTES` 说明测法 |
| **10.5.1** | **Desktop Bridge 与 Win32 产品必须始终具备隐私政策** | `site/privacy.html` + `PRIVACY.md`，且 `PRIVACY.md` **随包分发** |
| **11.2** | 不得侵犯第三方权利（含许可合规） | 随包 `LICENSE-THIRD-PARTY.txt`：Apache-2.0 归属（Lyricify-Lyrics-Helper）+ 内置 MiSans 许可说明 + FluentFlyout「未使用源码」声明。**三条分发渠道都要带**（MSIX / 便携 zip / NSIS 安装包） |
| **10.6** | 声明的能力必须与实际功能相关，不得绕过系统检查 | 仅 `runFullTrust`，名副其实 |
| **10.7** | 声明支持的语言必须本地化其描述文本；功能不全须说明 | 清单 `Resources` **只声明 `zh-CN`**（不虚报 en-US）；**商品页描述**（`STORE_LISTING_DESCRIPTION`）里写明「界面与歌词界面目前仅有简体中文」。注意：清单 `@Description` 因长度限制**没有**这句，别把两者混为一谈 |
| **10.9** | 通知须标注来源、不夹带无关推广、尊重系统开关 | 仅用托盘气泡提示自身状态，无推广、无 WNS |
| **11.1** | 元数据内容须符合 PEGI 12 / ESRB E10+ 或更低 | 全部为工具功能描述，无任何敏感内容 |
| **11.11** | 提交时须完成 IARC 年龄分级问卷并保持最新 | 见 §5 |
| **11.16** | 含实时生成 AI 内容须披露 | **不涉及**（无生成式 AI） |

## 8. 发新版流程

1. `lyrics_overlay.py` 里 `APP_VERSION` 升版本（MSIX 版本会自动补成四段）；
2. `store\build_store.py --fresh` 重新出包；
3. `store\build_store.py --listing` 刷新提审文案（版本号会写进认证说明）；
4. Partner Center → 该应用 → Packages → 替换 MSIX → 提交认证；
5. 认证通过后商店自动向用户推送更新（无需用户操作，也无需我们做任何事）。

⚠️ **商店版每次提审版本号必须比上次高**，不能重发同一版本号。

## 9. 常见拒审原因对照

| 拒审原因 | 本项目的规避 |
|---|---|
| 缺隐私政策（10.5.1） | 站点已就绪（`xiaohao8/music` → Netlify），提审时填 `site_url` 的两个地址 |
| 应用内自更新绕过商店（10.2.5） | `STORE_MODE` 短路 + 设置面板无更新入口 |
| 名称/描述与实际不符（10.1.1） | 描述如实写明 SMTC / 联网 / 语言三项限制；「关于」也按商店模式裁剪 |
| 启动即崩溃（10.4.2） | `audit_round3.py` offscreen 实例化 + refresh 全过；本地 `Add-AppxPackage` 实测 |
| 审核员测不出功能（10.3） | `CERTIFICATION_NOTES` 说明「需要播放器接入 SMTC 才会出歌词」 |
| 静默自启（10.2.8） | startupTask `Enabled="false"`，默认关闭且由系统管理 |
| 敏感权限滥用（10.6） | 仅 `runFullTrust`，无 `internetClient` 等多余声明 |
| 未做 IARC 分级（11.11） | 提审流程中完成问卷 |
| 语言虚报（10.7） | `Resources` 只声明 `zh-CN` |
| 走 HTTPS 直链安装器（10.2.9） | **不适用**——走 MSIX + Store 分发，不是直链安装器路线 |

## 10. 常见问题

**Q：`store/out/*.msix` 里为什么没有卸载脚本？**
A：商店应用的卸载由系统负责，包内放自定义卸载器会被认为多余甚至可疑。

**Q：为什么商店版把「进程保活」整个去掉了？**
A：MSIX 打包应用执行**包内另一个 exe** 时 `CreateProcess` 返回
`ERROR_ACCESS_DENIED` 且**不留任何日志**（WindowsAppSDK issue #4651）。
保活守护进程本质就是 `subprocess.Popen(sys.executable)`，在 MSIX 里必然失败。
而且商店应用的生命周期由系统托管，本就不需要保活。
所以 `spawn_supervisor()` 在商店模式直接短路，托盘与设置面板里的开关也一并隐藏。

**Q：`uap10:RuntimeBehavior` / `uap10:TrustLevel` 要不要显式声明？**
A：**不用**。这两个属性是 `Application` 元素的**可选**属性（有默认值），
且 `uap10` 命名空间自 Windows 10 2004（19041）才引入，而本包 `MinVersion`
是 17763。显式声明反而可能抬高实际最低系统要求。当前写法已通过
`makeappx` 的语义校验。

**Q：WACK 跑不起来？**
A：`appcert.exe` 需要管理员权限。非管理员环境下会 `Permission denied`，
这不是代码问题，换管理员终端再跑。

**Q：提审前还能自查什么？**
A：跑 `store\audit_round3.py`——它会强制 `STORE_MODE=True` 真实实例化浮层与设置面板、
走一遍 `refresh()`，并核对资产完整性、隐私政策与代码行为的一致性。
全部通过再上传，心里有底。
