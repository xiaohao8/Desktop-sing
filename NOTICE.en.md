# Third-Party Notices and Licensing (NOTICE)

While implementing its lyric engine and overlay interactions, Desktop-sing drew on the following
open-source projects. This file records **which capabilities were referenced**, **what their licences
are**, and **whether this project copied any of their source code**.

---

## 1. Lyricify-Lyrics-Helper

- Repository: https://github.com/WXRIW/Lyricify-Lyrics-Helper
- Author / copyright holder: **WXRIW**
- Licence: **Apache License 2.0**
- Language: C# (.NET)

### Capabilities referenced

| Capability | Corresponding implementation in this project |
| --- | --- |
| KRC (Kugou) lyric decryption | `decrypt_krc()` |
| KRC / YRC / LRC format parsing | `parse_krc()` / `parse_yrc()` / `parse_lrc()` |
| Automatic lyric format detection (`TypeHelper`) | `detect_lyric_format()` / `parse_lyrics_auto()` |
| Whole-timeline offset (`OffsetHelper`) | `offset_lines()` |
| Downgrading word-level lyrics to line-level | `downgrade_to_lines()` |
| LRC generation / export | `generate_lrc()` |
| Kugou online search and retrieval (`Providers/Web/Kugou`) | `fetch_kugou_search()` / `fetch_kugou_lyric()` |
| Multi-source search and matching (`SearchHelper` / `CompareHelper`) | `_match_candidates()` / `score_lyrics()` / `fetch_lyrics()` |
| LRCLIB lyric source | `fetch_lrclib_candidates()` |
| Detecting and handling info lines (title lines / copyright notices / credits) | `is_info_line()` / `_INFO_PAT` / `_CREDIT_PAT` |
| Chinese Traditional to Simplified conversion | `to_simplified()` / `T2S_PARTIAL` |

### Implementation approach

This project is a **clean-room Python reimplementation**: only algorithmic ideas, data format
conventions and interface boundaries were drawn from the original. **No C# source code was copied
line by line**, and no compiled artefacts from it are included.

### Licence obligations

The following notice is provided as required by section 4 of the Apache License 2.0:

```
Portions of this software are derived from Lyricify-Lyrics-Helper
Copyright (c) WXRIW
Licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
```

> Note: the full Apache-2.0 licence text is available at
> https://github.com/WXRIW/Lyricify-Lyrics-Helper/blob/master/LICENSE

Lyricify-Lyrics-Helper itself credits the following third-party code, listed here for completeness:

- LyricParser (MIT License) — https://github.com/HyPlayer/LyricParser
- 163MusicLyrics (Apache-2.0 License) — https://github.com/jitwxs/163MusicLyrics

### Sources not integrated

Lyricify also supports Soda Music, Apple Music (TTML), Musixmatch, Spotify and other sources. This
project does **not** integrate them, because each requires per-user credentials (Apple Music needs a
Media User Token, Spotify needs an `sp_dc` cookie, Musixmatch needs a User Token), which does not fit
this app's zero-configuration design.

---

## 2. FluentFlyout

- Repository (original): https://github.com/unchihugo/FluentFlyout
- Developed by: Hugo Li (unchihugo) and others
- Licence: **GNU General Public License v3.0**
- Language: C# / WPF

### What was referenced

**UI and interaction design concepts only**, for example:

- Customisable overlay position (`POSITION_PRESETS` / `_apply_position_preset()`)
- Smooth entrance and exit animations
- Screenshot / tray residency, Fluent 2 look and feel

### Important statement

**This project uses no source code, resource files or compiled artefacts from FluentFlyout.**
Because FluentFlyout is licensed under GPL-3.0 and this project did not copy its code,
**this project's licensing is not subject to GPL-3.0**.

Concepts, interaction paradigms and visual styles are not themselves protected by copyright; every
feature listed above was implemented independently in this project.

---

## 3. This project's own dependencies

See `requirements.txt`. Third-party Python packages (PySide6, winsdk and others) each follow their
own original licences.
