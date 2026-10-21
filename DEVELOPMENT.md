# DEVELOPMENT.md — building, internals, contributing

This document covers everything needed to build CCV from source, understand how it works, and ship a release. For the user-facing intro see [README.md](README.md). For AI-agent rules, see [CLAUDE.md](CLAUDE.md).

## Repository layout

```
ccv/
├── ccv.py                  # the entire app, single file (~4500 lines)
├── requirements.txt        # pillow, pywin32, pycaw, comtypes
├── assets/
│   ├── icon.png            # 512×512 source for the app icon
│   ├── icon.ico            # multi-res ICO embedded in ccv.exe
│   └── README.md
├── bin/                    # ffmpeg/ffplay/ffprobe (gitignored, distributed via release)
├── installer/
│   └── ccv.iss             # Inno Setup script for ccv-setup.exe
├── .github/
│   ├── FUNDING.yml
│   └── workflows/
│       └── release.yml     # CI: build exe/zip/installer + publish to GitHub Releases on tag
├── CHANGELOG.md
├── CLAUDE.md               # rules for AI agents working in this repo
├── DEVELOPMENT.md          # ← you are here
├── LICENSE
└── README.md               # user-facing
```

`ccv.py` is intentionally a single file. The cost (a long file) is paid for by the benefit (one file to ship, one file to read, no import maze). If it ever grows past ~6000 lines, that calculus changes.

## Stack

- **Python 3.11+** (3.13 is what CI uses).
- **Tkinter** (`tk` / `ttk`) for the GUI — no Qt, no Electron, no web views.
- **ffmpeg** captures via DirectShow and outputs raw matroska to stdout. **ffplay** consumes a copy of that stream for the preview. A second ffmpeg instance consumes another copy for recording.
- **Win32** (`pywin32`) is used for: `SetParent` (reparent ffplay's HWND inside the Tk window), `SetWindowPos` with `SWP_NOREDRAW` (jank-free sidebar slide), clipboard, and shortcut creation.
- **pycaw** for live audio session volume / mute (no ffplay restart needed).
- **PyInstaller** to bundle into a single `.exe`.

## Architecture sketch

```
                  ┌────────────────────────────┐
                  │ master ffmpeg (dshow)      │
                  │  -c:v copy  -c:a pcm_s16le │
                  │  matroska → stdout         │
                  └──────────────┬─────────────┘
                                 │
                       ┌─────────▼──────────┐
                       │ Python _StreamTee  │
                       │  (init segment +   │
                       │   per-consumer Q)  │
                       └────┬────────┬──────┘
                            │        │
                  ┌─────────▼─┐    ┌─▼──────────────┐
                  │ ffplay    │    │ ffmpeg recorder │
                  │ (preview) │    │ (re-encode)     │
                  └───────────┘    └─────────────────┘
```

Key decisions:

- **Single capture, multiple consumers.** The capture card is opened once. `_StreamTee` replicates the matroska stream byte-for-byte to each consumer (preview + recorder), and replays the matroska init segment when a consumer joins mid-stream. This is how recording start/stop doesn't restart the preview.
- **Embedded preview, not a second window.** ffplay is launched with `-noborder`, then we `SetParent(ffplay_hwnd, tk_hwnd)` and resize it to fit a Tk frame. No flash, no second taskbar entry.
- **Low-latency tuning.** `nobuffer`, `low_delay`, `flush_packets`, `cluster_size_limit=100ms` on the matroska muxer.

## Development setup

You need Python 3.11+ and a copy of ffmpeg/ffplay/ffprobe somewhere on the system.

```sh
git clone https://github.com/manucruzleiva/ccv
cd ccv
pip install -r requirements.txt
```

Drop `ffmpeg.exe`, `ffplay.exe`, and `ffprobe.exe` into `bin/`, **or** make sure they're on your `PATH`. Recommended source: [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases) → `ffmpeg-master-latest-win64-gpl.zip`.

Run the GUI:

```sh
python ccv.py
```

CLI subcommands (useful while debugging):

```sh
python ccv.py preview     # preview-only, no GUI
python ccv.py screenshot  # one-shot capture
python ccv.py record      # record until Enter
python ccv.py devices     # list DirectShow devices
python ccv.py shortcut    # create a Desktop .lnk
python ccv.py build       # produce ccv.exe via PyInstaller
```

## Building `ccv.exe` locally

```sh
python ccv.py build           # --onefile, portable, ~135 MB (slow startup, ~1-2s extract)
python ccv.py build --onedir  # --onedir, instant startup, distribute the whole folder
```

The build picks up `bin/ffmpeg.exe`, `bin/ffplay.exe`, `bin/ffprobe.exe` and the contents of `assets/` and bakes them into the `.exe`. Output lands at `./ccv.exe`.

To build the installer locally, install [Inno Setup 6](https://jrsoftware.org/isinfo.php), run `python ccv.py build --onedir` and then, from the repo root:

```sh
iscc /DAppVersion=0.8.0 installer\ccv.iss   # -> dist/ccv-setup.exe
```

If PyInstaller fails on the `update_exe_pe_checksum` step with `PermissionError`, that's Windows Defender real-time-scanning the freshly written `.exe`. Re-run the build; the second pass usually goes through.

## Releasing

Tagged releases are built and published automatically by [`.github/workflows/release.yml`](.github/workflows/release.yml) — push a tag matching `v*` and CI does the rest.

1. Bump `APP_VERSION` in `ccv.py`.
2. Add a `## [X.Y.Z] — YYYY-MM-DD` section in `CHANGELOG.md`, plus the link reference at the bottom.
3. Open a PR with both changes, get it merged.
4. Tag and push:
   ```sh
   git tag v0.7.0
   git push origin v0.7.0
   ```
5. Watch the **Release** workflow run on GitHub Actions. When it's green, the release is published with `ccv-setup.exe`, `ccv-portable.zip`, `ccv.exe` and `SHA256SUMS.txt` attached. The workflow refuses a tag that doesn't match `APP_VERSION`.

Asset names are fixed (no version in them) and the in-app updater depends on them: renaming any of them, or dropping `SHA256SUMS.txt`, breaks auto-update for every installed copy. The installer's `AppId` in `installer/ccv.iss` must never change either, or upgrades stop finding the previous install.

### Distribution modes and OTA updates

`detect_install_mode()` decides how this copy was shipped, which decides what the updater downloads:

| Mode | Detected by | Update asset | How it's applied |
|---|---|---|---|
| `installed` | `unins000.exe` next to the exe | `ccv-setup.exe` | run with `/SILENT` over the existing install |
| `portable_dir` | `_internal/` next to the exe | `ccv-portable.zip` | unzip, swap `_internal/` (rolled back on failure), copy over |
| `portable_exe` | neither | `ccv.exe` | replace the file |
| `source` | not frozen | — | the link opens the Releases page |

The flow is: `check_latest_release()` (GitHub API, background thread) → user clicks **Install** and confirms → `download_update()` (verifies SHA-256 against `SHA256SUMS.txt`) → `apply_update()` writes `%TEMP%\ccv-update\apply_update.ps1`, which waits for CCV to exit, applies the update, logs to `update.log` in the same folder and relaunches CCV (the old version if the update failed). Pre-releases and drafts are never offered.

Manual release (workflow dispatch) is also available from the Actions tab if you need to rebuild without a new tag.

### SemVer

- **MAJOR** — breaking change to the config schema, CLI, or supported platforms.
- **MINOR** — new feature or non-trivial behavior change.
- **PATCH** — bug fix, perf tweak, or doc-only change.

## Config

User preferences live at `~/.ccv.json` (or `ccv.json` next to the exe when a `ccv.portable` marker file sits beside it — the portable zip ships one). Anything that isn't immutable is persisted there: device choices, codec settings, theme, language, panel order, collapsed states, window geometry. The first launch migrates an older `~/.switch_capture.json` automatically.

`save_config()` is debounced via `_save_cfg()` — call the latter inside event handlers, never the former directly.

## Code conventions

- **Single-file by design.** Don't split modules unless the file gets unmanageable.
- **Themes via styles, not literals.** Don't hard-code palette colors in `ttk.Label(... foreground=...)` — register a named style in `_init_styles()` and reference it. Theme toggle wouldn't pick up literal colors.
- **No blocking popups for non-blocking info.** Use the status bar or a toast.
- **Translatable strings.** Anything user-visible goes through `self._t("key")` so language switch re-resolves it.

## Troubleshooting (dev)

- **Black preview / no signal:** check `python ccv.py devices` — if the card doesn't show up, the issue is upstream of CCV (driver, USB enumeration).
- **`pycaw` import fails:** install `comtypes>=1.4.0` explicitly; some `pycaw` versions don't pin it.
- **Tkinter looks ugly on HiDPI:** that's a Tk issue, not CCV. The fix is `ctypes.windll.shcore.SetProcessDpiAwareness(2)` — already done early in `ccv.py`.

## Credits

- [ffmpeg](https://ffmpeg.org) — the entire video pipeline.
- [pycaw](https://github.com/AndreMiras/pycaw) — Windows Core Audio session control.
- [Pillow](https://python-pillow.org) — clipboard / image conversion.
- [pywin32](https://github.com/mhammond/pywin32) — Win32 API bindings.
- [PyInstaller](https://pyinstaller.org) — single-file packaging.
