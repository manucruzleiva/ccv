# CLAUDE.md — guidance for AI agents working on CCV

This file is read automatically by Claude Code (and similar coding agents) when they enter the repo. Anything here is treated as a binding instruction for how to work on the project.

For full project context (architecture, build, internals, contributing), read [DEVELOPMENT.md](DEVELOPMENT.md). For the user-facing intro, see [README.md](README.md). The file below is intentionally short and only covers the rules that are easy to violate.

## Hard rules

### 1. Always update the changelog

Whenever you add a feature, fix a bug, change behavior, or refactor anything user-visible, you **must** update [CHANGELOG.md](CHANGELOG.md) **in the same commit** as the code change. No exceptions.

- Use [Keep a Changelog](https://keepachangelog.com) sections: `Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security`.
- Each bullet should be one sentence describing the user-visible effect (or the under-the-hood change if no UX impact). Don't paste commit hashes.
- If there's no entry for the current version yet, create a new heading at the top following SemVer.

### 2. Bump the version on every release

[ccv.py](ccv.py) holds `APP_VERSION` near the top of the file. Bump it according to SemVer (see [DEVELOPMENT.md](DEVELOPMENT.md#semver) for the breakdown). When you bump `APP_VERSION`, also add the matching `## [X.Y.Z] — YYYY-MM-DD` heading in `CHANGELOG.md` and the link reference at the bottom of that file.

### 3. Releases are built by CI, not by hand

Pushing a tag matching `v*` triggers [`.github/workflows/release.yml`](.github/workflows/release.yml), which builds `ccv.exe` on a Windows runner and publishes a GitHub Release with the `.exe` attached. Don't run `python ccv.py build` and `gh release create` manually unless CI is broken — divergence between hand-built and CI-built binaries is a maintenance trap.

### 4. The version label in the GUI links to the GitHub CHANGELOG

Don't reintroduce an in-app changelog popup. Clicking the version label in the **System** panel opens `APP_CHANGELOG_URL` (`https://github.com/manucruzleiva/ccv/blob/main/CHANGELOG.md`) in the user's default browser. The single source of truth for release notes is the file in the repo.

### 5. Author identity for commits inside this repo

The repo-local `git config` is set to:
```
user.name  = manucruzleiva
user.email = 153244278+manucruzleiva@users.noreply.github.com
```
Don't change these and don't commit with a global identity that exposes a real email.

## Don'ts (style)

- Don't add `messagebox` popups for non-blocking info — prefer toasts or status bar.
- Don't bake palette colors into `ttk.Label(... foreground=...)` literals; use a named style configured by `_init_styles()` so theme toggle works.
- Don't bypass `_save_cfg()` debouncing — call it after any cfg mutation, never `save_config()` directly inside event handlers.
