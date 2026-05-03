# Changelog

All notable changes to **CCV — Capture Card Viewer** are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Release workflow YAML no longer fails to parse. The previous fix added a comment that contained the literal `${{ }}` token sequence, which GitHub Actions evaluates as an empty templating expression and refuses to schedule. Comment rephrased to describe the same behavior without that token.
- Release workflow no longer crashes when the CHANGELOG section for the tag contains backticks. The notes are now written to `release-notes.md` and passed via `--notes-file` instead of being interpolated into a bash string (which caused tokens like `\`PrintScreen\`` to be evaluated by the shell).

## [0.7.0] — 2026-05-03

### Added
- `PrintScreen` keyboard shortcut: triggers a screenshot when the CCV window is focused (no-op when preview is not running). Tooltip on the 📷 button mentions the shortcut.
- New **Output folders** sidebar panel (`sec.folders`) — single, dedicated place to set the destination directories for screenshots and recordings.
- GitHub Actions workflow ([`.github/workflows/release.yml`](.github/workflows/release.yml)): builds `ccv.exe` on `windows-latest` and publishes a GitHub Release with the `.exe` attached on every `v*` tag push (also runs manually via workflow_dispatch). Manual hand-built releases are no longer the supported path.
- [DEVELOPMENT.md](DEVELOPMENT.md) — architecture, stack, dev setup, build process, code conventions, troubleshooting. CLAUDE.md is trimmed to agent-specific rules and points at DEVELOPMENT.md for context.
- README rewritten as a user-facing pitch: "play and record your console inside Windows" framing, comparison vs OBS / vendor apps, FAQ section, sponsor CTA. Repo About description updated to match.
- CLAUDE.md rule: commit messages must explain the *why*, not just the what.

### Changed
- Path inputs for `screenshot_dir` and `video_dir` moved out of the **Captura** / **Grabación** panels into the new **Carpetas de salida** panel — one place to manage output locations, no duplicated UI.

## [0.6.0] — 2026-05-03

### Added
- App icon (`assets/icon.ico`, multi-resolution 16/32/48/64/256) generated from `assets/icon.png` and embedded into `ccv.exe` by PyInstaller.
- README: keyboard / mouse shortcuts reference (F11, F12, Esc, video gestures, Ctrl+click button shortcuts).
- `.github/FUNDING.yml` pointing to GitHub Sponsors (`manucruzleiva`); repo's Sponsor button is enabled.
- Project renamed: `Switch Capture` → **CCV (Capture Card Viewer)**.
- Window/taskbar icon support via `assets/icon.ico` + `assets/icon.png`. Sets `AppUserModelID` so Windows groups the app under its own taskbar icon instead of inheriting Python's.
- Persistent layout: panel order, collapsed/expanded states, window geometry survive across sessions.
- Help text (`?` buttons) is now an i18n hover tooltip instead of a popup. Spanish + English variants ship.
- `--onedir` build mode for instant startup (vs. default `--onefile` which extracts to `%TEMP%`).
- Bundled `ffmpeg.exe`/`ffplay.exe` from `bin/` are baked into the .exe via `--add-binary`, plus `assets/` via `--add-data`.
- Auto-migration: `~/.switch_capture.json` → `~/.ccv.json` on first launch.

### Changed
- `?` help button replaced with hover tooltip (no more popup interruption).
- `_StreamTee.remove_recorder` now closes recorder stdin directly (EOF immediate) instead of waiting for the queue to drain — stop-record latency drops from up to 15s to <3s.
- Recorder tags output as `bt709` TV-range to match preview color reproduction.
- Stop-record button gives immediate visual feedback (disabled state) so the user doesn't double-click.
- Sidebar slide animation rewritten with Win32 `SWP_NOREDRAW` fast-path: ffplay's HWND glides without per-frame repaint.
- Top-bar buttons unified under one style/dimension; window controls and quick toggles grouped.
- `?` help tooltip + window/section text is fully translatable; format-matrix strings re-render on language switch.
- Light theme panel headers no longer default to the dark navy "card top" look.

### Removed
- Sidebar show/hide button. Use focus mode (double-click on video, `Esc`, or ⤢) to toggle the layout.
- In-app changelog popup. The version label in the System panel now opens this file on GitHub.
- README: `pip install` / `python ccv.py` / build instructions. README now assumes the user runs the bundled `ccv.exe`.

### Fixed
- Native window chrome no longer flashes on startup (window is `withdraw`'d during build, revealed once ready).
- DirectShow device enumeration runs in a background thread → first-paint of the GUI is instant.
- Panel headers re-color reliably on theme toggle (`apply_palette` reads from `P[...]` directly).
- Sidebar position toggle (`⇆`) now actually swaps left/right (previous bug: `_target` was being reassigned during build).

## [0.5.0] — 2026-05-03

### Added
- Mute toggle: middle-click on the video, or 🔊/🔇 button in the top bar.
- Volume control via mouse wheel over the video, with floating overlay.
- Custom title-bar window controls (close / maximize / fullscreen / minimize).
- Primary actions (Preview, Screenshot, Record) moved to the top bar.
- Keyboard shortcuts: `F11` fullscreen, `F12` minimize, `Esc` exit fullscreen.

### Changed
- Low-latency tuning: `-fflags nobuffer`, `-flags low_delay`, `-flush_packets`.
- Diagnostics, config save, and embed resize all debounced for fluid UI.

### Fixed
- Window no longer drifts when collapsing/expanding panels after maximizing.
- Click on panel headers no longer kicks off an accidental drag (`return "break"`).
- Drag has a 5px threshold to avoid jitter.

## [0.4.0] — 2026-05-03

### Added
- Live dark/light theme toggle (no window restart).
- Native OS chrome removed; custom controls + drag from anywhere in the window.
- Ctrl+Click on Capture/Record opens the corresponding folder in Explorer.
- Hover tooltips on all buttons.
- Tooltip on combos shows the underlying cfg variable name.
- Live status and Diagnostics panel merged into the System section.

### Fixed
- App icon now visible in the taskbar (`WS_EX_APPWINDOW` style bit).

## [0.3.0] — 2026-05-02

### Added
- Collapsible panels (▼/▶) and reorderable (↑/↓).
- Right-side sidebar collapsible (▶/◀).
- Embedded preview inside the main window (no more secondary window).
- Buttons with emoji + tooltips.
- Actionable fix buttons in the Diagnostics panel.

### Changed
- Embed sync follows window resize events.

## [0.2.0] — 2026-05-02

### Added
- Diagnostics panel with live warnings (unsupported resolution, no NVENC GPU, etc.).
- Interactive Resolution+FPS matrix (click a green cell to apply).
- GPU detection + codec advisor in the Recording panel.
- Screenshots taken from the preview buffer (no device touch, instant).
- Recording in parallel to the preview.

### Fixed
- Capture ffplay's `stderr` to surface real errors in a message box.
- Stream changed from NUT to Matroska + audio re-encoded to PCM (fixes 'Invalid argument' in the muxer).

## [0.1.0] — 2026-05-02

### Added
- Initial client with compact tkinter GUI.
- Preview with audio, PNG screenshots (clipboard + file), video+audio recording.
- ffmpeg auto-installer and Desktop shortcut.
- CLI subcommands: `preview`, `screenshot`, `record`, `install`, `build`, `devices`.

[0.7.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.7.0
[0.6.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.6.0
[0.5.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.5.0
[0.4.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.4.0
[0.3.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.3.0
[0.2.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.2.0
[0.1.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.1.0
