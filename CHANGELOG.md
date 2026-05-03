# Changelog

All notable changes to **CCV — Capture Card Viewer** are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] — 2026-05-03

### Added
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

[0.6.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.6.0
[0.5.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.5.0
[0.4.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.4.0
[0.3.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.3.0
[0.2.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.2.0
[0.1.0]: https://github.com/manucruzleiva/ccv/releases/tag/v0.1.0
