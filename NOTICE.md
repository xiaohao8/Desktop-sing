# 第三方来源与许可说明（NOTICE）

桌面歌词（Desktop-sing）在实现歌词引擎与悬浮交互时，参考了以下开源项目。
本文件说明**参考了哪些能力**、**许可是什么**、以及**本项目是否复制了对方源码**。

---

## 1. Lyricify-Lyrics-Helper

- 仓库：https://github.com/WXRIW/Lyricify-Lyrics-Helper
- 作者 / 版权方：**WXRIW**
- 许可：**Apache License 2.0**
- 语言：C#（.NET）

### 参考的能力

| 能力 | 本项目对应实现 |
| --- | --- |
| KRC（酷狗）歌词解密 | `decrypt_krc()` |
| KRC / YRC / LRC 格式解析 | `parse_krc()` / `parse_yrc()` / `parse_lrc()` |
| 歌词格式自动识别（`TypeHelper`） | `detect_lyric_format()` / `parse_lyrics_auto()` |
| 时间轴整体偏移（`OffsetHelper`） | `offset_lines()` |
| 逐字降级为逐行 | `downgrade_to_lines()` |
| LRC 生成 / 导出 | `generate_lrc()` |
| 酷狗在线搜索与取词（`Providers/Web/Kugou`） | `fetch_kugou_search()` / `fetch_kugou_lyric()` |
| 多来源搜索与匹配（`SearchHelper` / `CompareHelper`） | `_match_candidates()` / `score_lyrics()` / `fetch_lyrics()` |
| LRCLIB 歌词来源 | `fetch_lrclib_candidates()` |
| 识别并处理信息行（标题行 / 版权声明 / 制作名单） | `is_info_line()` / `_INFO_PAT` / `_CREDIT_PAT` |
| 中文简繁转换 | `to_simplified()` / `T2S_PARTIAL` |

### 实现方式

本项目是 **Python 重写实现（clean-room reimplementation）**：只借鉴了算法思路、数据格式约定
与接口划分，**没有逐行复制对方的 C# 源码**，也没有引入其编译产物。

### 许可义务

以下声明按 Apache License 2.0 第 4 条要求给出：

```
Portions of this software are derived from Lyricify-Lyrics-Helper
Copyright (c) WXRIW
Licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
```

> 说明：Apache-2.0 的完整许可正文见
> https://github.com/WXRIW/Lyricify-Lyrics-Helper/blob/master/LICENSE

Lyricify-Lyrics-Helper 自身还感谢了以下第三方代码，作为间接说明一并列出：

- LyricParser（MIT License）— https://github.com/HyPlayer/LyricParser
- 163MusicLyrics（Apache-2.0 License）— https://github.com/jitwxs/163MusicLyrics

### 未接入的来源

Lyricify 还支持汽水音乐、Apple Music（TTML）、Musixmatch、Spotify 等来源。
本项目**未接入**，原因是它们需要用户侧凭据（Apple Music 需要 Media User Token、
Spotify 需要 `sp_dc` Cookie、Musixmatch 需要 User Token），不适合本程序的零配置定位。

---

## 2. FluentFlyout

- 仓库（原始）：https://github.com/unchihugo/FluentFlyout
- 开发：Hugo Li（unchihugo）等
- 许可：**GNU General Public License v3.0**
- 语言：C# / WPF

### 参考的内容

**仅参考 UI 与交互设计概念**，例如：

- 浮层位置可定制（`POSITION_PRESETS` / `_apply_position_preset()`）
- 平滑的入场 / 出场动画
- 截图 / 托盘常驻、Fluent 2 观感

### 重要声明

**本项目没有使用 FluentFlyout 的任何源码、资源文件或编译产物。**
由于 FluentFlyout 采用 GPL-3.0，而本项目并未复制其代码，因此
**本项目的许可不受 GPL-3.0 约束**。

概念、交互范式与视觉风格本身不受著作权保护；上述功能均由本项目独立实现。

---

## 3. 本项目自身的依赖

见 `requirements.txt`。第三方 Python 包（PySide6、winsdk 等）各自遵循其原始许可。
