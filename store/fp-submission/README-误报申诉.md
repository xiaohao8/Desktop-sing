# PyInstaller 误报申诉材料（Trojan:Python/ShellLoader 家族）

## 背景
- 2026-10-03 21:18 Windows Defender 拦截**商店已发布版 1.0.1.0** 的主程序：
  `Trojan/Python.ShellLoader.am`，路径
  `C:\Program Files\WindowsApps\A135C2AE.Desktop-sing_1.0.1.0_x64__8ahsnwh40hshg\Desktop-sing\Desktop-sing.exe`
  （操作类型「执行」、结果「处理失败」——WindowsApps 受包完整性保护，删不掉但启动被拦）。
- 2026-10-27 21:15 火绒在同一台机器、同一个包路径上命中同一特征
  `Trojan/Python.ShellLoader.am`（病毒ID 33030584079422A7），操作类型「执行」、
  结果「**已处理，删除文件**」——火绒直接把 exe 删了，商店版从此无法启动。
  父进程 `sihost.exe` 是 Windows 激活 MSIX 应用的正常进程，不是可疑调用方。
- 这是 PyInstaller 引导器的**通用启发式误报**（ShellLoader 家族专门命中未签名/商店签名的
  PyInstaller 打包程序），非真实恶意行为。本程序开源：https://github.com/xiaohao8/Desktop-sing

## 本目录文件（提交样本用）
| 文件 | 版本 | SHA256 | 用途 |
|---|---|---|---|
| `Desktop-sing-1.0.2.0-Desktop-sing.exe` | 1.0.2.0 | `7b506f67af3767a72053d07de809eea4fc33aeb25cf8b8f6c90cfb7d35cd4c06` | 待发布的 1.0.2 主程序，**提前报白** |
| `Desktop-sing-2.0.1.0-Desktop-sing.exe` | 2.0.1.0 | `faa548b2c7470b3bbd253a771aad8be5f417a33609c2d43ba803f385e6f07525` | 上一版提审包主程序 |

- 被拦的 1.0.1.0 原样本（`0921e0a61a86ddd25cf955578edb8c994d416ff90670c8647a90df8fe02112db`，
  2,142,499 字节）本机已无副本：它只存在于已安装的 WindowsApps 包里，被火绒删除后
  **只能从火绒隔离区「提取」取回**（「恢复」会因 WindowsApps 完整性保护失败）。
  提取到普通目录后再上传，别点「删除」。
- 1.0.2 样本是从便携版 zip 里取出的字节副本（zip 早于删除动作生成），
  哈希与构建产物一致。单独双击跑不起来——PyInstaller onedir 需要同目录 `_internal`。

## 本机立即解除拦截（管理员 PowerShell，Win+X →「终端(管理员)」）
```powershell
Add-MpPreference -ExclusionPath 'C:\Program Files\WindowsApps\A135C2AE.Desktop-sing_1.0.1.0_x64__8ahsnwh40hshg'
Add-MpPreference -ExclusionPath 'C:\Program Files\WindowsApps\A135C2AE.Desktop-sing_*'
Add-MpPreference -ExclusionProcess 'Desktop-sing.exe'
Add-MpPreference -ExclusionPath 'C:\Users\35436\Desktop\代码\desktop-lyrics'
```
- 第 1 条：当前已装的 1.0.1.0 包目录（精确）；第 2 条：带通配，覆盖以后 1.0.x 版本的包目录；
  第 3 条：按进程名排除（顺带覆盖 dist 里的免安装版测试 exe）；
  第 4 条：**项目构建目录**——2026-10-03 起 Defender 云端判定升级，任何新哈希的
  PyInstaller exe 落盘即删（旧哈希因判定缓存幸存），不加这条连构建产物都保不住。
  加完后重跑 `python build_exe.py --dir` 即可产出存活的 exe，再走 `store/build_store.py` 重打 msix。
- 加完直接试运行；若仍被拦：Windows 安全中心 → 保护历史记录 → 该条目 →「允许在设备上」。

## ⚠️ 上面那组命令只管 Defender，管不了火绒
`Add-MpPreference` 是 Defender 专用，火绒是独立引擎（`HipsDaemon`），两者互不影响。
本机被火绒拦时：
1. 火绒 → 安全日志 → 该条目 →「导出日志」（申诉要附）。
2. 火绒 → 隔离区 → 选中 `Desktop-sing.exe` →「**提取**」到普通目录（不是「恢复」）。
   **不要点「删除」**，样本是报白的唯一凭据。
3. 火绒 → 信任区 → 添加目录：整个程序目录（商店版为
   `...\WindowsApps\A135C2AE.Desktop-sing_<版本>_x64__8ahsnwh40hshg\Desktop-sing`）。
   WindowsApps 路径若加不进去，改用「按进程信任」添加 `Desktop-sing.exe`。
4. 文件已被删的，加信任后走「设置 → 应用 → 桌面歌词 → 高级选项 → **修复**」；
   修复无效再卸载重装。**不要**手动往 WindowsApps 里拷文件、不要改该目录 ACL——
   会破坏 MSIX 包完整性，后续更新与修复都会出问题。
5. 给用户的说法只能是「等厂商白名单」，长期让用户关实时防护不是解决方案。

## 火绒申诉渠道
- 火绒官方论坛「样本上报 / 误报反馈」区发帖，标题格式
  `[样本误报]【疑似误报复核】<软件名> 的 <文件名> 被报 <病毒名>`；
  同时在火绒客户端「反馈」入口提交一份。
- 必附：被拦的原始 exe（zip/7z 压缩）、火绒导出的安全日志、拦截截图、开源地址。
  只给哈希和日志通常不足以精确解除。
- 正文要写清：软件来源与发行渠道、检测名与完整路径、大小与 SHA256、触发场景
  （`sihost.exe` 拉起 MSIX 属系统正常激活流程）、已做的核查、以及四个诉求
  （是否误报 / 命中了什么特征 / 能否修规则并加白 / 还需什么材料）。
- 一次把 1.0.1.0（已发布被拦）、1.0.2.0（待发布）两个样本一起交，避免新版本上线再撞一次。
- 发帖/回执状态记在本文件末尾「进度」。

## 火绒论坛发帖正文（可直接复制）

标题：

```
[样本误报]【疑似误报复核】桌面歌词 Desktop-sing 的 Desktop-sing.exe 被报 Trojan/Python.ShellLoader.am
```

正文：

```
软件名称：桌面歌词 Desktop-sing（Windows 桌面悬浮歌词，开源个人项目）
开源地址：https://github.com/xiaohao8/Desktop-sing
发行渠道：Microsoft Store（PFN A135C2AE.Desktop-sing_…8ahsnwh40hshg）+ GitHub Releases

一、被拦详情
检测名：Trojan/Python.ShellLoader.am（病毒ID 33030584079422A7）
路径：C:\Program Files\WindowsApps\A135C2AE.Desktop-sing_1.0.1.0_x64__8ahsnwh40hshg\Desktop-sing\Desktop-sing.exe
大小 2,142,499 字节；SHA256 0921e0a61a86ddd25cf955578edb8c994d416ff90670c8647a90df8fe02112db
时间 2026-10-27 21:15:08，操作类型「执行」，结果「已处理，删除文件」
操作进程 C:\Windows\System32\sihost.exe（父进程 svchost.exe）——这是 Windows 激活
MSIX 应用的正常流程，不是可疑调用方。
另附待发布的 1.0.2.0 主程序：2,981,730 字节，
SHA256 7b506f67af3767a72053d07de809eea4fc33aeb25cf8b8f6c90cfb7d35cd4c06

二、为什么判断是误报
1. 程序用 PyInstaller（Python 3.12 + PySide6）打包，ShellLoader 家族是命中
   PyInstaller 引导器的通用启发式特征，同族误报在开源社区大量存在。
2. 该 exe 已经过微软 Store 签名分发，1.0.1.0 上架时通过入库扫描；同一份字节
   在 2026-10-03 也被 Windows Defender 报过同特征，属跨厂商同类启发式。
3. 源码公开可审：全部功能为读取本机 SMTC 播放状态并绘制透明悬浮窗，
   无网络上传、无自删除/注入/计划任务/注册表启动项以外的敏感行为（开机自启
   仅在用户勾选时写 HKCU 的 Run 键，可在设置里关闭）。
4. 构建侧已主动降低可疑特征：关闭 UPX 加壳（--noupx + spec upx=False），
   商店包不再附带第二个未签名 exe（watchdog.exe），版本资源字段完整
   （CompanyName / FileDescription / OriginalFilename / LegalCopyright）。
5. 未做 Authenticode 签名是个人项目成本考虑，如实说明；需要的话我可以补充
   构建脚本、依赖清单、构建机信息。

三、诉求
1. 请确认是否为误报；
2. 若为误报，请告知命中的具体规则/特征 ID，便于我针对性规避；
3. 能否把上述两个 SHA256 加入白名单，并考虑对「Store 分发的 PyInstaller 未签名
   引导器」这条启发式做规则修正（否则每个新版本上线都会被删一次，用户体验是
   「应用打不开」）；
4. 还需要什么材料，我按清单补齐（样本已按论坛要求 zip 压缩上传）。

附：火绒安全日志导出（含上述条目）、拦截弹窗截图、GitHub 仓库与 Store 页面链接。
```

发帖前确认：附件用**隔离区「提取」出来的 1.0.1.0 原件**（不是重新构建的产物），
`Desktop-sing-1.0.2.0-Desktop-sing.exe` 单独 zip；日志用「安全日志 → 导出日志」。

## 申诉渠道（两条都走）
1. **精确样本**（优先）：Windows 安全中心 → 病毒和威胁防护 → 保护历史记录 →
   找到 ShellLoader 条目 →「操作」→ **还原 / 允许在设备上**，并选 **提交给我们分析（报告为误报）**。
   这里提交的是被拦截的那个 1.0.1.0 原样本，微软白名单最精准。
2. **网页提交**（覆盖下一个版本）：https://www.microsoft.com/en-us/wdsi/filesubmission
   - 上传本目录的 `Desktop-sing-1.0.2.0-Desktop-sing.exe`（1.0.2 已发布，主样本）；
     旧版 `Desktop-sing-2.0.1.0-Desktop-sing.exe` 作为历史样本一并说明即可；
   - 应用名称/软件说明：桌面歌词 (Desktop-sing) 开源桌面歌词悬浮条，PyInstaller 打包；
   - 补充说明：Microsoft Store 已发布应用（PFN `8ahsnwh40hshg`），Defender 报
     Trojan:Python/ShellLoader.AM，确信为 PyInstaller 通用误报，请审查并加白。

## 为什么必须做
- 商店签名挡不住本地 Defender 的这条启发式（1.0.1.0 已是 Store 签名仍被拦）→
  **所有装了商店版的用户都会遇到同样的「报毒无法运行」**，直接等差评/卸载。
- 1.0.2.0 提审时微软入库还会再扫一遍；提前申诉把白名单铺好，降低认证被拦概率。

## 1.0.2 已做的降误报改造（可写进申诉说明）
- 构建关闭 UPX 加壳（`--noupx` + spec `upx=False`）——加壳 PE 是启发式高风险特征。
- 商店包不再附带 `watchdog.exe`：商店版本就不启用保活，少一个未签名 exe 少一处扫描面。
- 修正 exe 版本资源注入：此前 `version_info.txt` 被手改后，动态替换静默失配，
  产物版本号会永远停在模板旧值（现为按字段名正则替换，不再依赖旧值）。
- 出包防呆：MSIX 只认目标版本的 onedir，缺目录直接失败，不再回退旧产物打新号包。
- 版本资源齐（CompanyName / FileDescription / LegalCopyright / OriginalFilename）+ 真实图标。
- 未做代码签名：个人项目暂不购证，申诉时如实说明，并强调外层 MSIX 由微软签名。

## 进度
- 2026-10-03 Defender 命中 1.0.1.0，已按上文提交微软（WDSI + 保护历史记录）。
- 2026-10-27 火绒命中 1.0.1.0 并删除文件；待办：
  1. 从火绒隔离区提取 1.0.1.0 样本 + 导出安全日志；
  2. 论坛发误报复核帖（附 1.0.1.0 与 1.0.2.0 两个样本）；
  3. 本机加信任区 → 修复商店版；
  4. 等回执，若 1.0.2 仍命中则走 1.0.3 只改构建特征的热修。
- 2026-10-30 **本机杀软已换为 Kaspersky + 腾讯管家**（火绒已卸载，上文火绒待办作废）。
  v1.0.3 冻结 exe 在新目录执行即被拦（秒退、无崩溃事件、文件保留；1.0.2 的 exe
  挪到 %TEMP% 同样被杀、原目录可跑）——按路径/哈希的执行拦截，与 2026-10-27
  火绒「删执行不删落盘」同构。v1.0.3 的冻结自检待在 Kaspersky / 管家里放行
  `dist\Desktop-sing-v1.0.3\` 后补跑；1.0.2 自 10-29 起未被任何引擎再命中。

## 已完成（2026-10-27 晚，v1.0.2 全渠道发布）
- GitHub Release `v1.0.2` 三资产齐：`Desktop-sing-v1.0.2-setup.exe` 26,124,266 B /
  `Desktop-sing-v1.0.2-portable.zip` 34,254,127 B / `SHA256SUMS.txt`；远端哈希与本地构建一致。
- **`releases/latest` 已指向 v1.0.2**：把 v2.0.1 / v2.0.0 标为 prerelease——GitHub 按语义版本
  取最高，2.0.1 > 1.0.2，不标就会把 1.0.2 的用户倒回旧构建；旧页面与下载链接都保留。
- `update.json` 的 `url` 写死 v1.0.2 安装版直链，同样为了不依赖 latest 排序。
  蓝奏云 1.0.2 链接待上传后补三处：`LANZOU_MIRRORS`、`update.json` 的 `lanzou_*`、官网两卡 href。
- 官网 `https://music.202271.xyz` 已部署 v1.0.2（下载卡与版本号）。
- 商店包 `store/out/Desktop-sing-1.0.2.0-x64.msix`（35.0 MB，包内无 `watchdog.exe`）
  SHA256 `fd5e0abf5a16eb92e78f0aebd2c6f4e0d1e6eb628f6bba4192078ba71de4f22d`；
  待办：Partner Center 上传，文案见 `store/out/listing-v1.0.2.md`。
- 自检：`smoke_test.py` 36/36 通过，`store/audit_round3.py` FAIL 0 / WARN 0。

## 构建期实测：火绒删的是「执行」，不是「落盘」
- 2026-10-27 会话中火绒**边构建边删**：新 exe 在执行时被删（安全日志操作类型＝执行、
  结果＝已处理删除文件），写完不运行的文件能留在磁盘上。所以 v1.0.2 的冻结版 exe
  **当天没跑过 `--selftest`**，验证只到静态：PE 版本资源 1.0.2.0、无 UPX 段、python312、
  5 个 winrt 命名空间齐、未签名。
- 真机自检步骤：先把 `dist\Desktop-sing-v1.0.2` 整个目录加进火绒信任区，再跑
  `Desktop-sing.exe --selftest`（实现见 `lyrics_overlay.py` 的 `_selftest()`：写
  `selftest.txt` 后退出，不拉守护进程、不改配置）。
- exe 若再次消失：从 `dist/release/桌面歌词-v1.0.2-免安装极速版.zip` 重新解压
  （zip 生成早于删除动作，字节完好）。**不要重新构建**——重建出来的哈希是新的，
  白名单还没铺到它上面。

## 已完成（2026-10-29，火绒放行后补跑冻结版自检）
- 火绒信任后，从便携 zip 恢复原始 `Desktop-sing.exe`，没有重新构建。
- 主程序版本 `1.0.2.0`，SHA256 保持
  `7B506F67AF3767A72053D07DE809EEA4FC33AEB25CF8B8F6C90CFB7D35CD4C06`。
- `Desktop-sing.exe --selftest` 退出码 `0`；`selftest.txt` 结果为 `RESULT PASS`。
- `desktop-lyrics.log` 记录：`SMTC ok`、`fonts ok`、`render ok (5 styles)`。
- 冻结版运行自检硬门槛已通过，可以进行 Partner Center 上传前检查。
