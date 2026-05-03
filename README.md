# CCV — Capture Card Viewer

Lightweight Windows client for USB capture cards (Switch, PS5, Xbox, retro consoles…). Single Python file, embeds ffplay's preview inside a tkinter window and uses ffmpeg for recording — no OBS, no Electron, no browser engine. Roughly 50 MB of memory at runtime.

![screenshot placeholder](assets/screenshot.png)

## Features

- **Embedded preview** — ffplay is reparented into the main window via Win32 `SetParent`. No second window, no flash on toggle.
- **Seamless recording** — start/stop the recorder without restarting the preview. A Python tee replicates the master ffmpeg matroska stream to multiple consumers (preview + recorder) and replays the init segment for mid-stream pickup.
- **Low latency tuning** — `nobuffer`, `low_delay`, `flush_packets`, 100 ms matroska clusters.
- **Live volume / mute** — scroll wheel over the video. Middle-click to mute. Volume changes apply live via Windows audio sessions (`pycaw`), not by restarting ffplay.
- **Focus mode** — double-click the video, sidebar slides out, video fills the window. Win32 fast-path keeps ffplay smooth during the animation.
- **Persistent layout** — panel order, collapsed states, window geometry, and all settings survive across sessions.
- **i18n** — Spanish and English live-switchable; help text and tooltips re-resolve at hover time.
- **Light & dark themes** — switchable live, no restart.

## Download

Grab `ccv.exe` from the [Releases](https://github.com/manucruzleiva/ccv/releases) page and run it. Standalone — bundled ffmpeg/ffplay, no Python or system-wide install needed.

CLI subcommands (optional):

```
ccv.exe             # GUI (default)
ccv.exe preview     # preview-only via terminal
ccv.exe screenshot  # one-shot capture
ccv.exe record      # record until Enter
ccv.exe devices     # list DirectShow devices
ccv.exe shortcut    # create a Desktop .lnk
```

## Shortcuts

**Keyboard**

| Key   | Action                                               |
|-------|------------------------------------------------------|
| `F11` | Toggle fullscreen                                    |
| `F12` | Hide window to tray                                  |
| `Esc` | Exit focus mode (and exit fullscreen if active)      |

**Mouse — over the video**

| Gesture           | Action                                         |
|-------------------|------------------------------------------------|
| Double-click      | Toggle focus mode (sidebar slides out)         |
| Scroll wheel      | Volume ±5% per step                            |
| Middle-click      | Toggle mute                                    |

**Mouse — over the action buttons**

| Gesture                   | Action                            |
|---------------------------|-----------------------------------|
| `Ctrl` + click on `📷`    | Open the screenshots folder       |
| `Ctrl` + click on `⏺`     | Open the recordings folder        |

## Config

User preferences live at `~/.ccv.json` and include device choices, codec settings, theme, language, panel order, collapsed states, window geometry. The first launch migrates an older `~/.switch_capture.json` automatically.

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

## License

MIT — see [LICENSE](LICENSE).

## Credits

- ffmpeg / ffplay — https://ffmpeg.org
- pycaw — Windows Core Audio bindings
- Pillow — clipboard / image conversion
- pywin32 — Win32 clipboard and shortcut helpers
