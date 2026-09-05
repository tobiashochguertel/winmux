# WinMux fork

This repository is a **fork** of [ZimengXiong/winmux](https://github.com/ZimengXiong/winmux),
a sidebar-first window manager for macOS.

## Fork status

- **License:** MIT — original copyright (c) 2026 Zimeng Xiong, fork copyright (c) 2026 Tobias Hochgürtel
- **License compliance:** REUSE (see `.reuse/dep5` and `LICENSES/`) — `reuse lint` / `mise run lint-license` to verify
- **Branch model:**
  - `main` — tracks the latest upstream release tag (stable)
  - `dev.patch` — tracks `upstream/main` (unstable, experimental patches)
- **Fork maintenance:** revert-then-repatch strategy — see [`.github/FORK-STRATEGY.md`](.github/FORK-STRATEGY.md)

## Remotes

| Remote | URL |
|--------|-----|
| `origin` | `https://github.com/tobiashochguertel/winmux` (this fork) |
| `upstream` | `https://github.com/ZimengXiong/winmux` |

## Workflows

- `.github/workflows/sync-upstream-and-fix.yml` — daily sync of `main` and `dev.patch` from upstream (07:00 UTC), re-applies `.github/patches/*.patch`
- `.github/workflows/update-upstream-prs.yml` — weekly refresh of `.github/UPSTREAM-PRS.md` (open upstream PRs catalog)
- `.github/workflows/reuse.yml` — REUSE license compliance check on pull requests

## Patches

Custom changes live in `.github/patches/` as `NNN-description.patch` files.
There are none yet. To add one, follow [`.github/FORK-STRATEGY.md`](.github/FORK-STRATEGY.md)
(never edit upstream files directly on `dev.patch`).

## Building

```bash
swift build        # build all products
swift test         # run tests
```

The app UI requires Xcode (see upstream `project.yml` + `makefile` for the
xcodegen-based build).