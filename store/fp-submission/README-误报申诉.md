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
- 第 1 条：当前已装的 1.0.1.0 包目录（精确）；第 2 条：带通配，覆盖以后 2.x 版本的包目录；
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

## 申诉渠道（两条都走）
1. **精确样本**（优先）：Windows 安全中心 → 病毒和威胁防护 → 保护历史记录 →
   找到 ShellLoader 条目 →「操作」→ **还原 / 允许在设备上**，并选 **提交给我们分析（报告为误报）**。
   这里提交的是被拦截的那个 1.0.1.0 原样本，微软白名单最精准。
2. **网页提交**（覆盖下一个版本）：https://www.microsoft.com/en-us/wdsi/filesubmission
   - 上传本目录的 `Desktop-sing-2.0.1.0-Desktop-sing.exe`；
     （1.0.2 出包后换传 `Desktop-sing-1.0.2.0-Desktop-sing.exe`）；
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
