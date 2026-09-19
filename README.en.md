# Desktop-sing

> 简体中文: [README.md](README.md)

An always-on-top lyrics overlay for the Windows desktop. It reads whatever is currently playing —
any player that integrates with the Windows system media controls, such as QQ Music, NetEase Cloud
Music or Kugou — and shows the album art together with karaoke-style line-by-line lyrics. The colour
scheme is derived from the album art automatically.

> **Note on language:** the application interface is currently **Simplified Chinese only**. The
> English files in this repository (`README.en.md`, `USAGE.en.txt`, `PRIVACY.en.md`, `NOTICE.en.md`)
> document the app for English-speaking users, but the UI strings themselves are not translated yet.

## Features

- **Follows playback automatically** — reads the current track (title / artist / album / artwork /
  position) through the Windows System Media Transport Controls (SMTC), and switches when the track
  changes. With several players open at once it follows the one that is actually playing. Playback
  position is **continuously corrected**: the overlay extrapolates from wall-clock time locally, so
  small player jitter, delayed reports, or even a frozen position report (audio keeps playing but the
  player stops reporting a position) will not stall the lyrics. Only seeking, dragging, or a large
  jump backwards triggers a re-align.
- **Lyrics matching across multiple sources** — prefers the source matching the current player,
  otherwise queries the available public lyrics sources in turn. Each source is first scored on
  **quality** (a word-level timeline is preferred, then a translation), and the search stops early
  once a full "word-level + translation" result is found. Results are cached locally, so replays are
  instant.
- **Word-level (karaoke) lyrics** — rendered word by word when the source supplies a word-level
  timeline, otherwise advanced evenly within the line.
- **Lyrics cleanup** — drops blank lines and symbol-only lines, strips **copyright notices and
  production credits** (lines shaped like "role + colon", so normal lyrics are not damaged), keeps
  only the first of duplicate lines sharing a timestamp, and re-sorts everything by time.
- **Traditional → Simplified conversion (optional)** — ships with 900+ common character mappings.
  Drop a full mapping table at `%APPDATA%\Desktop-sing\t2s.tsv` (one "traditional<TAB>simplified"
  pair per line) to override the built-in table. Unmapped characters are left untouched.
- **5 overlay styles** — Native Float / Glass Capsule / Album Card / Vinyl / Soundwave, switchable
  from the context menu or the tray menu.
- **Karaoke visuals**
  - The current line is filled with a travelling gradient taken from the album art's dominant colour.
  - That same colour drives the capsule background, border, equaliser and progress bar.
  - Lines slide and fade in, the capsule width transitions smoothly, and an equaliser pulses next to
    the title while playing.
  - **Ambient glow** — a radial halo in the album's dominant colour sits behind the card and breathes
    gently with the music.
- **Translated / romanised lyrics** — when the source provides per-line translations or
  romanisations they are parsed and matched to the corresponding line, then shown below the current
  line in a smaller size and a secondary colour (toggleable).
- **9 word-by-word animations** — flowing sweep / rise-up / scale-in / plain fade / bounce-in /
  wave / fan-out / typewriter / none. Driven per **word**, not per line, so a character animates
  exactly when it is sung.
- **Font library (one-click download of free-for-commercial-use fonts)** — six bundled font choices
  (DingTalk JinBuTi / MiSans / Alibaba PuHuiTi 3.0 / Noto Sans SC / LXGW WenKai / Smiley Sans), all
  free for commercial use. One click downloads, installs and applies them. Downloads use a primary
  CDN with automatic fallback to mirrors.
- **Desktop integration** — borderless always-on-top overlay, drag to move (position is remembered),
  click-through, **position lock** (prevents accidental drags), tray icon control, and
  **auto fade-out on pause**.
- **Position presets (7 anchors)** — bottom centre (just above the taskbar, the default), top centre,
  screen centre, and the four corners, switchable from the context menu or the tray menu. What is
  stored is an **anchor relative to the screen's working area**, not absolute coordinates, so it stays
  correctly docked after a resolution change, a taskbar height change, or plugging in an external
  display. Dragging the overlay manually drops it into "free placement" and remembers the coordinates.
- **Global hotkeys** — `Ctrl+Alt+P` play/pause, `Ctrl+Alt+,` / `.` previous/next track,
  `Ctrl+Alt+[` / `]` lyric offset, `L` show/hide, `S` settings, `T` style, `D` display mode,
  `G` lock position, `B` ambient screensaver. **Disabled by default** so they do not fight with other
  software; combinations already taken are skipped and reported.
- **Ambient screensaver (4 styles, black background, burn-in friendly)** — a full-screen idle screen:
  pure black background plus a large halo in the album's dominant colour, a dim large clock, and the
  current lyric. Every element drifts on a **different slow period**, so nothing stays pinned long
  enough to burn in. Can be set to start after N minutes idle (10 by default), will not re-trigger
  while the system is locked, and exits on any keypress or mouse click.
- **Run at startup + process supervision** — autostart is written to the registry Run key; a
  lightweight supervisor process restarts the app after it is force-killed or crashes (with backoff so
  a crash loop cannot spin). Choosing "Exit" in the app is a normal exit, and the supervisor goes with
  it.
- **Settings panel** — a card-style dark UI grouped into Lyrics Sync / Appearance / Fonts / Overlay /
  Ambient Saver / System, with colours following the album art's dominant colour live.
- **Playback control** — previous / play-pause / next, a hover control strip, and double-click to
  play/pause; lyric offset calibration (±5 s); "Re-fetch lyrics" to manually correct a bad match.
- **Update check (built-in sources, works out of the box)** — no URL to fill in. The primary source is
  GitHub Releases, falling back in order to Gitee Releases → Gitee raw manifest → jsDelivr manifest;
  the highest version wins and any single source failing does not affect the others. Downloads are
  offered through both a mirror and GitHub. You can also point the update URL at your own GitHub or
  Gitee Releases, or a generic JSON manifest — leave it empty to restore the built-in sources.

## Settings

Everything lives in the settings panel and is saved automatically. All sliders are deliberately
**coarse (10% steps)**.

| Group | Item | Range |
| --- | --- | --- |
| Lyrics Sync | Lyric offset | -5 s … +5 s slider (0.5 s steps) plus early / late / reset buttons |
| Appearance | Overlay style | Native Float / Glass Capsule / Album Card / Vinyl / Soundwave |
| Appearance | Font | Fonts installed from the font library (MiSans is the default) plus curated system fonts |
| Appearance | Font size | 60% … 180% (10% steps); the card resizes with it |
| Appearance | Opacity | 30% … 100% (10% steps) |
| Appearance | Word animation | Flowing sweep / rise-up / scale-in / plain fade / bounce-in / wave / fan-out / typewriter / none |
| Appearance | Edge fade | Toggle plus fade width 0–60 px (10 px steps) |
| Appearance | Display mode | Desktop (stay behind windows) / Always on top |
| Appearance | Artwork / translated lyrics / progress time | Three toggles |
| Fonts | 6 free-for-commercial-use fonts | One-click download (a few MB up to 26 MB); the button turns into "Use" once installed |
| Overlay | Ambient glow / auto fade on pause / position lock / click-through | Toggles, plus "Reset position" and "Preview screensaver" buttons |
| Ambient Saver | Style / start when idle / threshold / only when idle | 3D Particles / Minimal / Soundwave Bars / Orbits, plus a 3–60 minute threshold |
| System | Run at startup / process supervision / global hotkeys / check for updates on launch | Toggles, an update-URL field (empty = built-in sources) and a "Check now" button |

---

## Building and development

### 1. Requirements

Windows 10/11 and Python 3.8+.

```bat
pip install -r requirements.txt
```

### 2. Running

```bat
pythonw lyrics_overlay.py             :: start without a console (or double-click 启动桌面歌词.bat)
python lyrics_overlay.py --selftest   :: self-test: probe SMTC sessions + render all 5 styles
```

None of the offscreen scripts (tests, previews, diagnostics) need a display or a real media player.
The only prerequisite is:

```bat
set QT_QPA_PLATFORM=offscreen
```

### 3. Packaging the exe

Qt6/PySide6 needs **PyInstaller 5+** (older versions bundled with the system Python are too old).
Create a build virtualenv once, using `--system-site-packages` so the already-installed PySide6 and
winsdk are inherited without polluting the system environment:

```bat
python -m venv .buildenv --system-site-packages
.buildenv\Scripts\python.exe -m pip install -U "pyinstaller>=6"
```

After that, a release is a single command:

```bat
.buildenv\Scripts\python.exe build_exe.py            :: minimal (default)
.buildenv\Scripts\python.exe build_exe.py --full     :: with all bundled fonts (+15 MB)
.buildenv\Scripts\python.exe build_exe.py --no-font  :: no bundled fonts, smallest
.buildenv\Scripts\python.exe build_exe.py --dir      :: onedir build (starts faster)
```

- The version number comes from `APP_VERSION` in `lyrics_overlay.py`.
- Outputs carry a variant suffix and never overwrite each other: default / `-lite` (`--no-font`) / `-full`.
- `fonts/`, `winsdk` (the SMTC backend) and `Crypto` are collected automatically; **the whole pywin32
  family is excluded** — this project does not use it, and a stale install makes PyInstaller's
  pythoncom hook crash outright.
- `--icon` / `--version-file` are added automatically when `icon.ico` / `version_info.txt` exist.
- Older artefacts are moved into `dist\archive\` (renamed, never deleted), so any previous build can
  always be recovered.

### 4. Installer and portable build

```bat
.buildenv\Scripts\python.exe build_exe.py --dir   :: produce dist\Desktop-sing-v<version>\ first
python pkg_portable.py                            :: portable zip
makensis.exe installer\installer.nsi              :: installer exe (NSIS 3.11)
```

- **Installer** (NSIS): welcome → privacy statement (must be accepted) → install directory (defaults
  to `D:/Desktop-sing`, falling back to `%LOCALAPPDATA%\Desktop-sing` when there is no D: drive or the
  directory is not writable) → components → finish, with an option to launch immediately. A full
  uninstaller is included. Both install and uninstall detect and offer to close a running instance,
  and probe the target directory for actual write access, covering both the "file in use" and "no
  permission" failure modes.
- **Portable**: unpack and run. Contains the program plus its bundled documents (usage guide, privacy
  statement and third-party licences, each in Chinese and English).
- The source directory and output name in `pkg_portable.py` contain the version number (currently
  hard-coded to v1.0.0), so a new release needs those updated too.
- The uninstall script copies itself to `%TEMP%` before running, which lets it remove the program
  directory including itself. The installer's uninstaller additionally clears the autostart entry and
  **asks** whether to delete local configuration and cache.

### 5. Regression tests

```bat
python smoke_test.py
```

Runs 30+ offscreen cases: word-level timelines, translation mapping, rendering of all 5 styles,
control-strip hit testing, the settings panel, frame-by-frame checks of all 9 word animations,
screensaver rendering and layout gates, lyric format detection and parsing, multi-source fetching
(stubbed, no network), the config sandbox, and hover control-strip avoidance. The tests temporarily
rewrite the config and restore it afterwards.

> **Render assertions must use `grab()`, never `render(pixmap)`.** In this environment
> `QWidget.render(pm)` draws nothing at all (the result comes back fully transparent), so the
> assertion passes silently while verifying nothing. `widget.grab()` really does run `paintEvent`
> (and does not require calling `show()` first).

### 6. Project layout

```
lyrics_overlay.py          main program (single file)
smoke_test.py              offscreen regression tests
preview_render.py          preview image generation (light and dark background per style)
_cfg_sandbox.py            shared config sandbox for diagnostics (per-script backup + cross-process lock)
_diag_*.py                 quantitative diagnostics: performance / visual A-B / layout / screensaver
_diag_update_lanzou.py     update-source logic checks (multi-source probing / mirror mounting / version compare)
_diag_update_dialog.py     offscreen render checks for the update dialog (buttons and link layout)
update.json                manifest mirror content (read directly by jsDelivr; bump on release)
build_exe.py               build the exe
pkg_portable.py            build the portable zip
sign_release.py            release integrity check and code signing (skips signing when no certificate)
check_ver.py               verify version info in built artefacts
installer/installer.nsi    NSIS installer source
store/                     Microsoft Store (MSIX) pipeline: manifest template, asset generation, packaging, submission guide
store/README-STORE.md      full submission guide (package identity, local self-signed testing, WACK, checklist)
README.md / README.en.md   project documentation (Chinese / English)
使用说明.txt / USAGE.en.txt bundled user guide (Chinese / English)
PRIVACY.md / PRIVACY.en.md privacy statement (Chinese / English)
NOTICE.md / NOTICE.en.md   third-party notices and licensing (Chinese / English)
LICENSE-THIRD-PARTY.txt    third-party licences and attribution shipped with the app
启动桌面歌词.bat            double-click launcher (pythonw, no console)
卸载桌面歌词.bat            portable uninstall: cleans the program directory and config
site/                      landing page (plain static HTML/CSS/JS, no build step, no CDN dependencies)
site/privacy.html          privacy policy page (the URL required for Store submission; same source as PRIVACY.md)
site/privacy.en.html       English privacy policy page (same source as PRIVACY.en.md)
site/tools/make_assets.py  landing-page image generator (derives assets/ from preview/)
fonts/                     MiSans shipped with the app (falls back to a system font if missing)
preview/                   preview image output
```

The landing page is a single static page (HTML + CSS + plain JS, no CDN or framework). Copying the
whole `site/` directory to any static host is enough; opening `site/index.html` locally works too.

---

## Releases and security

### Why the first run gets blocked

The program has **no code-signing certificate** (Authenticode certificates are a yearly cost, and
personal projects usually start without one). Windows SmartScreen treats a new exe that is both
unsigned and not yet widely downloaded as untrusted by default, so a blue warning appears on first
launch. It is not a sign of a problem with the program — it just lacks reputation. Allow it once.

### How to allow it

| Situation | What to do |
|---|---|
| Blue "Windows protected your PC" | Click **More info** → **Run anyway** |
| Edge / Chrome warns "this file may be dangerous" | In the download bar click **… → Keep**; if it was deleted, restore it from Downloads → "Show blocked content" |
| Antivirus heuristic false positive | Add the program directory to your trusted/allowed list (unsigned PyInstaller builds are commonly flagged by heuristics) |
| Verify the file was not tampered with | See "Verifying the file" below |

### Verifying the file

Every release writes `SHA256SUMS.txt` into `dist/release/`; ship it alongside the release assets.

```bat
certutil -hashfile 桌面歌词-v1.0.0-安装版.exe SHA256
```

Compare the output against the matching line in the manifest. A match means the downloaded file is
byte-identical to the build output (this protects against a replaced host or mirror, but it does
**not** prove authorship — only code signing does that). The repository also ships `sign_release.py`,
which recomputes the checksums and reports the signature status of every artefact in one command:

```bat
python sign_release.py            :: compute SHA256 + report signature status + write SHA256SUMS.txt
python sign_release.py --sign     :: sign every exe (only signs if a certificate is configured; otherwise skips, exit code still 0)
```

### Adding code signing later

The signing slots are already wired up, and **a missing certificate does not affect the build
pipeline at all**. Once a certificate is available, set the environment variables and run
`python sign_release.py --sign`. The password goes through environment variables only — never the
shell history, never the repository.

| Variable | Purpose |
|---|---|
| `SIGN_PFX` / `SIGN_PWD` | Path to the PFX/PKCS#12 file and its password (certificates on a token may have an empty password and prompt interactively) |
| `SIGN_THUMBPRINT` | Alternative: the SHA1 thumbprint of a certificate in the store (pair with `SIGN_STORE`, default `My`) |
| `SIGN_TIMESTAMP` | RFC3161 timestamp service, default `http://timestamp.digicert.com` (with a timestamp the signature stays valid after the certificate expires) |
| `SIGN_DESC` / `SIGN_URL` | Signature description and product homepage (optional) |
| `SIGN_TOOL` | Path to `signtool.exe`; if unset it is located in the local Windows SDK |

Worth knowing: an **EV certificate establishes reputation immediately** (SmartScreen essentially stops
warning), while an **OV certificate still needs download volume** to have the warnings taper off.
Both require organisational or individual identity vetting.

### Microsoft Store pipeline

The Store build uses a separate MSIX pipeline that does not interfere with the GitHub/mirror
distribution above:

```bat
.buildenv\Scripts\python.exe store\build_store.py --fresh   :: rebuild + produce the MSIX
```

At runtime the Store build switches behaviour automatically (via `STORE_MODE` in `lyrics_overlay.py`):
updates always go through the Store (the in-app update channel is disabled, as Store policy requires),
autostart is delegated to the startupTask extension plus the system Startup settings page, and
uninstalling goes through system settings. See `store/README-STORE.md` for the full submission steps.

## Known limitations

- The player must integrate with the system media controls (recent QQ Music and NetEase builds do by
  default; some older builds or mini-player modes may not).
- When a song is not covered by any lyrics source, matching may fall back to a cover version —
  **a cover's per-line timing does not necessarily line up with the original recording**.
- The NetEase source needs `pycryptodome` for its search and lyric endpoints; without it the app falls
  back to a legacy endpoint with worse matching quality.
- Translated lyrics depend on whether the source provides them; fallback sources usually have no
  translation.
- Word-level (karaoke) timing depends on the source. Line-level sources try to borrow the word-level
  timeline of the same track, and advance evenly within the line when that is not possible.
- Some platforms' sources only provide line-level lyrics today; word-level timing for their exclusive
  tracks is filled in from other sources where available.
- Production-credit detection is **heuristic** — it keys on "role word + colon", so unusual phrasings
  can slip through.
- The built-in Traditional→Simplified table is a **high-frequency character list**; rarer characters
  are left as-is. Supply your own `t2s.tsv` for full conversion.
- Apple Music (TTML), Spotify and Musixmatch are **not supported**: they require per-user credentials,
  which is at odds with this app's zero-configuration design.
- Global hotkeys need exclusive key combinations. Combinations already taken are skipped and reported
  when you enable the feature, which is **off by default**.
- The font library uses a primary source with mirror fallback; if all of them fail the button becomes
  "Retry".
- The ambient screensaver's idle detection uses `GetLastInputInfo`; watching video still counts as
  user input.
- Once packaged as an exe, the `fonts/` directory may not be writable, so the font library always
  downloads into `%APPDATA%\Desktop-sing\fonts`.
- The interface is currently **Simplified Chinese only**; no English UI is available yet.

## Credits and licensing

This project drew on the **ideas** of the following open-source projects. Both were reimplemented in
Python; no source code was copied.

- **[Lyricify-Lyrics-Helper](https://github.com/WXRIW/Lyricify-Lyrics-Helper)** (WXRIW, Apache-2.0) —
  lyric format parsing, automatic format detection, timeline offset and downgrade, online lyric
  retrieval, multi-source search matching, and lyric optimisation (info-line handling, Traditional to
  Simplified conversion).
- **[FluentFlyout](https://github.com/unchihugo/FluentFlyout)** (Hugo Li et al., GPL-3.0) —
  UI/interaction concepts only (customisable overlay position, smooth entrance animation).
  **None of its source code is used.**

See **[NOTICE.en.md](NOTICE.en.md)** for the complete licensing obligations and notices, and
**[LICENSE-THIRD-PARTY.txt](LICENSE-THIRD-PARTY.txt)** for the notices shipped to end users.
