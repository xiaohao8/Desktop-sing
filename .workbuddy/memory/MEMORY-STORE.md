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

## 文档体系与对外口径（2026-09-19 确立）

- **文档分两层，规则不同**：
  - **对外**（`README.md` / `使用说明.txt` / `site/*` / `PRIVACY.md` / `NOTICE.md` 及各自 `.en`）：
    说功能、用法、限制、隐私、许可、放行；**不说**逆向细节。
  - **开发者**（README 的「构建与开发指南」章节、`store/README-STORE.md`）：构建/打包/测试/踩坑照写。
- **中英各一份，共 4 组对应**：`README.md↔README.en.md`、`PRIVACY.md↔PRIVACY.en.md`、
  `NOTICE.md↔NOTICE.en.md`、`使用说明.txt↔USAGE.en.txt`；另有 `site/privacy.en.html`
  （英文页区提审填这个 URL）与 `site/privacy.html`，两页互相有语言切换链接。
- **对外文档禁词**（审计 P5.16 已锁）：`3DES`、`weapi`、`AES-CBC`、`RSA 无填充`、
  `ghfast.top`、`ghproxy.net`、`周杰伦`。删的理由分三类：
  ① 逆向/规避技术措施（逆向记录进公开文档＝不必要的法律暴露）；
  ② 第三方代理服务点名（脆弱且易被质疑）；
  ③ 对具体艺人与平台版权状况举例（毫无必要）。
  **例外**：`NOTICE.md` / `LICENSE-THIRD-PARTY.txt` 的**函数名映射表必须保留** ——
  Apache-2.0 第 4 条归属义务要求「指明了什么被借用」，属「该说」，别一刀切删。
- **界面语言必须如实声明（政策 10.7）**：界面只有简体中文、无 i18n → 三处口径：
  ① 清单 `Resources` **只**声明 `zh-CN`（`store/AppxManifest.template.xml` 里，**不在** build_store.py）；
  ② **商品页描述** `STORE_LISTING_DESCRIPTION` 写明「界面…仅有简体中文」；
  ③ 英文 `README.en.md` 写明 `the application interface is currently Simplified Chinese only`。
  不写＝暗示有英文界面，按 10.1.1 判「描述不准确」。
  注意清单 `@Description` 因长度限制**没有**这句，别和商品页描述混为一谈。
- **随包文档统一 5 份，三渠道同验**：`LICENSE-THIRD-PARTY.txt` / `PRIVACY.md` /
  `使用说明.txt` / `PRIVACY.en.md` / `USAGE.en.txt`。
  分发时中文改名（`第三方许可.txt` / `隐私声明.txt`），英文用 ASCII 名
  （`Privacy-EN.txt` / `Usage-EN.txt`）避免跨平台编码问题。
  ⚠️ 早先 **MSIX 漏了使用说明**（MSIX 布局来自 onedir，onedir 里没有使用说明）
  → 商店用户装完找不到任何说明；审计 `P5.12h` 现在逐渠道校验整份清单。
- **⚠️ makeappx 会对非 ASCII 路径做百分号编码**：`使用说明.txt` 在 .msix 的 zip 里是
  `%E4%BD%BF%E7%94%A8%E8%AF%B4%E6%98%8E.txt`。审计比对文件名前**必须先
  `urllib.parse.unquote`**，否则中文名永远「像没打进包」（安装后 Windows 会解码回原名，功能无问题）。
- **NSIS 是否真嵌入文件只能反证**：整包 LZMA，从 exe 抽字符串验不了。
  做法：临时移走待验文件 → 跑 `makensis` → 应报 `File: "..." -> no files found.` 且退出码 1 → 还原。
  （`File` 指令源文件缺失时 makensis 必然报错，所以编译成功本身就说明找到了文件。）

## 商店素材与截图（2026-09-19 修好后固化）

- **操作手册与参考手册分工**：`store/提审上线手册.md` = 从零到上架的**线性操作清单**
  （准备 → 出包 → 验收 → 逐字段提交 → 发布后 → 卡点速查）；
  `store/README-STORE.md` = **参考手册**（商店版行为差异、13 条政策逐条对照、
  拒审原因表、FAQ）。改流程改前者，改原理改后者。
- **商店截图**：`store/render_shots.py` 离屏生成 3 张 **1600×900** 到
  `store/out/shots/`（`store/out/` 不进仓库，换机器要重跑）。
  三张分别 = 等待态 / 有歌词（逐字高亮）/ 设置面板。
  ⚠️ 是**离屏合成图**（真实控件 + 合成壁纸），**不是真机截屏** → 提审建议另补 1 张真机图。
- **★ offscreen 抓图铁律：抓之前必须把控件里每一处动画推到终态。**
  无显示器的环境没有 event loop 推进动画，任何淡入/切行/缩放都会卡在第 0 帧，
  而且**失败是静默的**：`grab()` 返回**非 null 但全透明**的图，`isNull()` 判不出来，
  文件大小也正常，只有肉眼看才发现。本项目两处：
  - `SettingsPanel`：`showEvent()` 起 180ms 淡入 → opacity 停在 0
    → 需 `panel._fade.stop(); panel._fx.setOpacity(1.0)`（否则面板图是纯背景）；
  - `LyricOverlay`：切行动画把 `_line_t` 停在 0，而 `_apply_line_anim()` 会
    `setOpacity(_smoothstep(0) == 0)` → 整行歌词透明（只剩歌名）
    → 需 `ov._line_anim.stop(); ov._line_t = 1.0`。
- **手动构造浮层状态时，绘制读的是缓存文本，不是 `lines[cur_idx]`**：
  必须自己喂 `_current_text` / `_next_text`，并设 `anchor_ts = time.monotonic()`
  （初值 0.0 配 `status="PLAYING"` → `_current_pos()` = 开机以来的秒数，行号全乱）、
  `anchor_pos`、`cur_idx`，最后 `_relayout()`。
  **别猜——直接照抄 `lyrics_overlay.py` 里的绘制自检写法（约 7462 行）**，
  那套早就摆对了。另外 `_relayout()` 可能自适应窗口尺寸（实测窗口 1000×320、
  pill 仅 394×136），所以**先 `grab()` 再按实际尺寸居中**，不要写死坐标。
- **截图属对外发布物**（进商品页）：只用自写占位歌词，
  **不要出现真实歌曲歌名/歌词、第三方播放器界面、受版权保护素材**。
  （审计 P5.17b 用禁词扫描锁住。）
- **判「截图是不是空白图」不能用透明度**：合成图整张 alpha 都是 255。
  用「相邻像素亮度突变数」（step=3/gap=4/thresh=25）：纯壁纸 **46**、
  idle **179**、hero **468**、settings **3870**，取 **120** 作分界。
- **商店 listing 图标**：根目录 `icon.png` 是 **1024×1024**，
  等比缩到 **300×300** 交上去（`store/assets/` 里最大只有 310×310）。

## 包标识：三项都要逐字符对，且能自证没抄错（2026-09-19 落地）

- Partner Center「产品管理 → 产品标识」里**被逐字符校验的有三项**，不是两项：
  `Package/Identity/Name`、`Package/Identity/Publisher`（`CN=<GUID>`）、
  **`Package/Properties/PublisherDisplayName`**。第三项最容易被忽略 —— 个人账号它**就是
  真实姓名**（本项目 `付志豪`），填成产品名会报
  *应用清单中的 PublisherDisplayName 元素…与发布者显示名称不匹配*。
  另有 `Package/Properties/DisplayName` 必须等于**已预留的应用名**之一，否则报
  *The name found in the package is not one of your reserved app names*。
- 本项目实测值：`A135C2AE.Desktop-sing` / `CN=815AB3D3-C7A7-40CB-93F0-57D02D5FAAF0` /
  `付志豪` / `桌面歌词|Desktop-sing`（**半角 `|`**）。
- **PFN 反推 —— 免费的自证手段（强烈建议每个包都做一次）**：
  `Package Family Name = <IdentityName>_<publisher_hash>`，后半段是**纯函数**：
  ```
  h = sha256(publisher.encode("utf-16-le")).digest()[:8]   # 取前 64 位
  big = int.from_bytes(h, "big") << 1                      # 64→65 bit：末位补 0
  hash13 = "".join(ALPHA[(big >> (5*(12-i))) & 31] for i in range(13))
  ALPHA = "0123456789abcdefghjkmnpqrstvwxyz"               # 去掉易混 i/l/o/u
  ```
  **`<< 1` 那步不能省**：13 字符 × 5 bit = 65 bit，少补这一位最后一字符必错
  （踩过：算出 `…hshh`，实际 `…hshg`，一度以为抄错了）。
  本项目反推 `8ahsnwh40hshg` == Partner Center 值 → **证明 `CN=…` 那串零抄错**。
  这套算法已固化进 `audit_round3.py` 的 **P5.20c3**：读 `identity.local.json` 的
  `package_family_name`，反推比对，不符即 FAIL。**抄错一个字符 → 哈希完全不同**，
  是「拒审第一大原因」目前唯一能在本地拦下的办法。
- **自检 P5.20 组（13 项）分工**：a/a2 本地标识是否填全（缺则 WARN）；
  b 站点根地址；c 「本地填了但 `out/` 还是旧包」；c2 包内三项与本地**逐字段**比对；
  c3 PFN 反推；d 应用名（含全角/半角 `|` 提示）＋包内 `DisplayName` 一致性；
  e 官网三页品牌标记与 `<title>`。
  **改标识/改名的唯一正确顺序**：改 `identity.local.json` → `build_store.py` →
  `audit_round3.py`（FAIL 0 / WARN 0）→ 上传。跳过中间那步就是「本地对、包里旧」。
- `store/identity.local.json` **必须 gitignored**（含发布者证书主题串），
  但 `package_family_name` 抄进来能让 c3 生效 —— 这段哈希不含敏感信息。
