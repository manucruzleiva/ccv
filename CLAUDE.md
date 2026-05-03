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

### 6. Commit messages must be clear and explain the *why*

Every commit message has a one-line subject (~70 chars max, imperative mood, no trailing period) followed by a body that describes the change in enough detail that a future reader doesn't have to read the diff to understand it.

- **Subject** — what the commit does, in one line. Don't dump file names; describe the user/dev-visible effect. Examples: `Reduce stop-record latency from 15s to <3s`, `Drop the in-app changelog popup`. Avoid generic openers like `Update X` or `Fix bug`.
- **Body** — wrap at ~72 chars. If the change spans more than one concern, use a bullet per concern. State the *why* and any non-obvious tradeoff, not just the *what*. The diff already shows what; the message has to add context the diff can't carry: motivation, prior incident, alternatives rejected, follow-up TODOs.
- **Don't paste commit hashes, issue links, or `Co-Authored-By` lines unless the user asked.** Don't write summaries that just recapitulate file names — those are visible in `git log --stat`.
- **Bad:** `Update README and add workflow`. **Good:** `Add CI release pipeline + rewrite README for end users` followed by a short body that says why the docs were split and what the workflow does.

A commit message is the only piece of context that travels with the commit forever. Treat it like documentation, not a confirmation receipt.

## Don'ts (style)

- Don't add `messagebox` popups for non-blocking info — prefer toasts or status bar.
- Don't bake palette colors into `ttk.Label(... foreground=...)` literals; use a named style configured by `_init_styles()` so theme toggle works.
- Don't bypass `_save_cfg()` debouncing — call it after any cfg mutation, never `save_config()` directly inside event handlers.
