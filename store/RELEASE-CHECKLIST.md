# 发版检查清单

这份清单不进入用户安装包。每次向 Microsoft Store 或 GitHub 发版，按顺序逐项核对；
任何一项失败都先停发，不要靠重新构建「碰运气」。

## 0. 先锁定产物，不再重建

- [ ] 本次版本只有一个候选构建目录，例如 `dist/Desktop-sing-v1.0.2/`。
- [ ] 记录每个交付文件的 SHA256、大小和构建时间。
- [ ] 已经开始申诉误报、上传审核或对外发布后，不再重建同版本产物。
      重建会改变哈希，让白名单、审核和更新清单全部对不上。

## 1. 版本号与文案一致

- [ ] `lyrics_overlay.py` 的 `APP_VERSION` 是本次版本，例如 `1.0.2`。
- [ ] `update.json` 的 `version` 与 `APP_VERSION` 完全一致。
- [ ] `update.json` 的 `url` 指向同一版本安装包，URL 中含 `v<版本>`。
- [ ] `site/index.html` 的 GitHub 安装版、便携版链接都指向同一版本。
- [ ] 没有镜像时，`update.json` 明确写 `lanzou_status`，且官网不承诺不存在的网盘入口。
- [ ] `store/out/listing-v<版本>.md` 的商品描述与实际能力一致。

## 2. 运行冻结后的 exe 自检（硬门槛）

先确认火绒信任区已包含整个解压目录，或按进程信任 `Desktop-sing.exe`。然后执行：

```powershell
& '.\dist\Desktop-sing-v1.0.2\Desktop-sing.exe' --selftest
$LASTEXITCODE
```

- [ ] 退出码为 `0`。
- [ ] `%APPDATA%\Desktop-sing\selftest.txt` 含 `RESULT PASS`。
- [ ] 同文件含 `SMTC ok`、`fonts ok`、`render ok (5 styles)`。
- [ ] 自检没有启动守护进程，也没有改写用户配置。
- [ ] 如果没有 Console 输出，仍以 `selftest.txt` 和退出码为准；两者缺一都算未通过。

> 2026-10-28 的 v1.0.2 当前状态：冻结 exe 尚未成功跑过 `--selftest`，
> 因为在火绒信任前主程序被执行拦截。向 Partner Center 上传 1.0.2.0 之前必须补跑。

## 3. PE 静态核对

```powershell
$exe = '.\dist\Desktop-sing-v1.0.2\Desktop-sing.exe'
(Get-Item $exe).VersionInfo | Select-Object FileVersion,ProductVersion
Select-String -Path $exe -Pattern 'UPX0|UPX!' -SimpleMatch
```

- [ ] `FileVersion` 与 `ProductVersion` 均为四段版本 `1.0.2.0`。
- [ ] 没有 `UPX0` / `UPX!` 标记，确认没有 UPX 加壳。
- [ ] 程序目录包含 `python312.dll`，不存在缺失运行时依赖。
- [ ] 结论记录到本次发布日志；静态检查通过不等于运行自检通过。

## 4. MSIX 核对

- [ ] `store/out/` 根目录只有一个待上传的 `.msix`。
- [ ] 包名中的版本为 `1.0.2.0`，架构为 `x64`。
- [ ] 包内没有 `watchdog.exe`。
- [ ] 包内含 `_winrt.pyd`，且清单引用的图标资产全部存在。
- [ ] 包内 `DisplayName`、`Publisher` 与 Partner Center 预留值逐字符一致。
- [ ] 上传前先走 Package Flight / 灰度，不直接全量覆盖旧版本。

## 5. Release 附件与哈希

- [ ] `SHA256SUMS.txt` 只列当前版本实际交付的两个文件：
      安装版 `.exe` 与便携版 `.zip`。
- [ ] 清单里的文件名与 GitHub Release 的 ASCII asset 名逐字一致。
- [ ] 本地重算的 SHA256 与清单一致。
- [ ] GitHub Release 的 `releases/latest` 指向本次稳定版，不带旧 prerelease。
- [ ] `update.json` 已同步到所有更新镜像源。

## 6. 发布后观察

- [ ] 从商店安装后，首次启动的待机文案是「已就绪」，不是加载中状态。
- [ ] 商店版设置面板没有应用内更新入口，自启入口打开系统「启动应用」页。
- [ ] 从旧版本触发检查更新会提示升级，当前版本不会误报。
- [ ] 观察 24 小时内的火绒/Defender 反馈；若再次误报，保留样本和拦截日志，
      不要在用户机器上要求关闭杀软。
- [ ] 记录商店认证结果、版本号、上架时间和灰度范围。
