# CLAUDE.md — guidance for AI agents working on CCV

This file is read automatically by Claude Code (and similar coding agents) when they enter the repo. Anything here is treated as a binding instruction for how to work on the project.

## Hard rules

### 1. Always update the changelog

Whenever you add a feature, fix a bug, change behavior, or refactor anything user-visible, you **must** update [CHANGELOG.md](CHANGELOG.md) **in the same commit** as the code change. No exceptions.

- Use [Keep a Changelog](https://keepachangelog.com) sections: `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`.
- Each bullet should be one sentence describing the user-visible effect (or the under-the-hood change if no UX impact). Don't paste commit hashes.
- If there's no entry for the current version yet, create a new heading at the top following SemVer.

### 2. Bump the version on every release

[ccv.py](ccv.py) holds `APP_VERSION` near the top of the file. Bump it according to SemVer:

- **MAJOR** — breaking change to config schema, CLI, or supported platforms.
- **MINOR** — new feature or non-trivial behavior change.
- **PATCH** — bug fix, perf tweak, or doc-only change.

When you bump `APP_VERSION`, also update the matching `## [X.Y.Z] — YYYY-MM-DD` heading in `CHANGELOG.md` and the link reference at the bottom of that file.

### 3. The version label in the GUI links to the GitHub CHANGELOG

Don't reintroduce an in-app changelog popup. Clicking the version label in the **System** panel opens `APP_CHANGELOG_URL` (`https://github.com/manucruzleiva/ccv/blob/main/CHANGELOG.md`) in the user's default browser. The single source of truth for release notes is the file in the repo.

### 4. Author identity for commits inside this repo

The repo-local `git config` is set to:
```
user.name  = manucruzleiva
user.email = 153244278+manucruzleiva@users.noreply.github.com
```
Don't change these and don't commit with a global identity that exposes a real email.

## Project shape

- Single-file Python app: `ccv.py` (~4500 lines). Tkinter GUI + ffmpeg/ffplay subprocesses.
- `bin/` holds local ffmpeg builds — gitignored, distributed via release asset, not via the repo.
- `assets/` holds the icon (`icon.png`, `icon.ico`) bundled into the .exe by PyInstaller.
- `~/.ccv.json` is the per-user config; `~/.switch_capture.json` is auto-migrated on first launch.

## How to ship a release

1. Bump `APP_VERSION` in `ccv.py`.
2. Add a section in `CHANGELOG.md` for that version.
3. Commit + push.
4. `python ccv.py build` → produces `ccv.exe` (~135 MB, includes bundled ffmpeg).
5. `gh release create v$VER ccv.exe --title "CCV v$VER" --notes-file release-notes.md` (or use `--notes` inline pulling from CHANGELOG).

## Don'ts

- Don't add `messagebox` popups for non-blocking info — prefer toasts or status bar.
- Don't bake palette colors into `ttk.Label(... foreground=...)` literals; use a named style configured by `_init_styles()` so theme toggle works.
- Don't bypass `_save_cfg()` debouncing — call it after any cfg mutation, never `save_config()` directly inside event handlers.
