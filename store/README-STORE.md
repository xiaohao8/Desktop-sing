# Microsoft Store（MSIX）发布指南

`store/` 目录专门负责微软商店发布线，与 GitHub/蓝奏云的分发渠道完全独立。

```
store/
├── AppxManifest.template.xml   清单模板（占位符由构建时替换，不要直接改它发布）
├── make_store_assets.py        生成全部商店图标资产（23 个，已跑通）
├── build_store.py              一键打包：布局组装 → 清单 → makeappx → 自检
├── assets/                     生成的图标资产（提交仓库，免得每次重渲染）
├── identity.local.json         ★ 你的包标识（本机填一次，勿提交、勿外传）
├── build/layout/               打包工作目录（可随时删）
└── out/Desktop-sing-x.y.z.w-x64.msix   最终产物
```

## 0. 为什么商店版行为不一样

| 行为 | 普通版 | 商店版（MSIX） |
|---|---|---|
| 更新 | GitHub/Gitee 查版本 + 蓝奏云下载 | **一律走商店**（`STORE_MODE` 已内置短路） |
| 开机自启 | 注册表 HKCU Run | **startupTask 扩展** + 系统「启动」设置页 |
| 卸载 | 自带卸载脚本 | 系统设置 → 应用（商店包不进包卸载脚本） |

代码里 `lyrics_overlay.py` 的 `is_msix_packaged()` 用
`kernel32.GetCurrentPackageFullName` 判断运行环境（非打包环境返回 15700），
打包后自动切到商店行为，**同一份代码同时出两种产物**。

## 1. 前置条件（一次性）

1. **Partner Center 开发者账号**：<https://partner.microsoft.com/dashboard>
   个人账号一次性注册费（约 $19 / 等值人民币，以官网为准），公司账号更贵。
2. **预留应用名称**：Partner Center → 新建应用 → 填名称「桌面歌词」。
   若被占用可试「桌面歌词 Desktop-sing」等变体——名称必须与清单里的
   `DisplayName` 一致，否则提审会被打回。
3. **拿到包标识**：应用 → 产品管理 → 产品标识，复制两样：
   - **包名**（Package/Identity/Name，形如 `12345Desktop-sing`）
   - **发布者**（Publisher，形如 `CN=1A2B3C4D-…`）

4. 写入本机标识文件 `store/identity.local.json`（此文件已进 `.gitignore` 思路：**勿提交**）：

   ```json
   {
     "name": "12345Desktop-sing",
     "publisher": "CN=1A2B3C4D-5E6F-..."
   }
   ```

   不填也能出包（占位标识），但**只能本地看结构，不能上传**。

## 2. 打包

```bash
# 用现有 dist/ 产物打包
.buildenv\Scripts\python.exe store\build_store.py

# 从源码全量重建再打包（提审前用这个，保证产物=当前代码）
.buildenv\Scripts\python.exe store\build_store.py --fresh
```

产物：`store/out/Desktop-sing-1.0.0.0-x64.msix`（未签名——**商店提审就传未签名包**，
微软会用它自己的证书重签）。

脚本自检项：包内必备文件（清单/四类图标/exe）、无卸载脚本残留、
清单无未替换占位符、版本四段数字。

## 3. 本地安装测试（自签名）

未签名的 MSIX 装不上，本地测试需要自签证书（管理员 PowerShell）：

```powershell
# ① 建自签证书（Subject 必须与清单 Publisher 一致！）
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=1A2B3C4D-5E6F-..." `
  -KeyUsage DigitalSignature -FriendlyName "Desktop-sing 本地测试" `
  -CertStoreLocation "Cert:\CurrentUser\My" -TextExtension @(
    "2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")

# ② 用它签 MSIX
signtool sign /fd SHA256 /a /f <证书导出pfx> /p <密码> `
  store\out\Desktop-sing-1.0.0.0-x64.msix

# ③ 信任该证书（仅本机测试用）
Export-Certificate -Cert $cert -FilePath test.cer
Import-Certificate -FilePath test.cer -CertStoreLocation "Cert:\LocalMachine\TrustedPeople"  # 需管理员

# ④ 安装
Add-AppxPackage -Path store\out\Desktop-sing-1.0.0.0-x64.msix
```

装上后重点验证：
- 托盘菜单「开机自启（系统设置）」能否跳转 `ms-settings:startupapps`；
- 设置面板：系统卡片是「打开启动设置」按钮、更新区是商店提示（无更新地址输入框）；
- 「检查更新…」菜单提示走商店；
- 歌词、屏保、快捷键等主功能与普通版一致。

## 4. WACK 认证（建议提审前跑）

```bash
.buildenv\Scripts\python.exe store\build_store.py --wack   # 需管理员权限
```

WACK（Windows App Certification Kit）就是商店审核用的测试集，
本地过了基本就不会栽在技术认证上。常见失败项见其报告，多为
「缺少 runFullTrust 声明」「启动崩溃」「架构不符」——本包都已规避。

## 5. 提审材料清单（Partner Center 页面填写）

| 材料 | 内容 | 备注 |
|---|---|---|
| 包 | 上传 out/*.msix | 未签名；每次提交版本号必须递增 |
| 名称 | 桌面歌词 | 与清单 DisplayName 一致 |
| 描述 | build_store.py 里 `DESCRIPTION` 同款文案 | 中英文各一份更稳 |
| 截图 | 至少 1 张，建议 1920×1080 起 | 桌面歌词实际运行效果 |
| 图标 | 商店 listing 图标（assets 里的可复用） | 300×300 PNG |
| 类别 | 音乐 / Music（次级：实用工具） | |
| 年龄分级 | 问卷如实填（无用户内容生成、无社交） | 通常全年龄 |
| **隐私政策 URL** | `site/privacy.html` 发布后的地址 | **必填**，缺失直接拒审 |
| 联系信息 | 邮箱 / 网站 | 审核沟通用 |

`site/privacy.html` 已写好（如实披露：本地存储、歌词接口按需查询、无账户无追踪），
随官网一起发布，把最终 URL 填进商店表单。

## 6. 发新版流程

1. `lyrics_overlay.py` 里 `APP_VERSION` 升版本（MSIX 版本会自动补成四段）；
2. `build_store.py --fresh` 重新出包；
3. Partner Center → 该应用 → Packages → 替换 MSIX → 提交认证；
4. 认证通过后商店自动向用户推送更新（无需用户操作，也无需我们做任何事）。

## 7. 常见拒审原因对照

| 拒审原因 | 本项目的规避 |
|---|---|
| 缺隐私政策 | `site/privacy.html` 已备 |
| 应用内自更新绕过商店 | `STORE_MODE` 短路，商店版无更新通道 |
| 名称/描述与实际不符 | 描述文案即功能清单，不夸大 |
| 启动即崩溃 | 本地 `Add-AppxPackage` 实测 + WACK |
| 敏感权限滥用 | 仅 `runFullTrust`，无 internetClient 等声明 |
| 静默自启 | startupTask `Enabled="false"`，默认关闭 |
