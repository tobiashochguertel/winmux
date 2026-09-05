# Changelog

All notable changes to this fork (tobiashochguertel/winmux) are documented
here. Changes are grouped by fork release; each entry references the
`.github/patches/` file it came from.

Upstream changes are tracked in upstream's GitHub releases — this changelog
covers fork-only modifications.

## [Unreleased] — dev.patch

### Added (PR #24, `001-cli-automation-and-sidebar-layer.patch`)

- **CLI automation** (`winmux` CLI, installable via `make cli-release`):
  - Project lifecycle: `create-project`, `list-projects`,
    `rename-project`, `set-project-color`, `delete-project` (guarded by
    `--action` + `--if-window-count`, never closes windows)
  - AeroSpace-style parsing: lazy `move-node-to-workspace new`, `--`
    disambiguation, JSON output, exit code 2 for usage errors
  - Agent pipeline: `agent query|check|apply` with explicit `--stdin`,
    schema + worldId validation, snapshot retries
- **Socket protocol v1** — versioned handshake, bounded frames,
  EOF/timeout handling. App and CLI must be installed as a matched pair.
- **Sidebar layering** — `workspace-sidebar.stay-on-top` config + Settings
  toggle (sidebar can render below the Dock)
- **Settings** — scroll position preserved across config reloads
- **Packaging** — `make release` builds a verified universal app+CLI pair
  with rollback; combined macOS archive; app-only Sparkle updates guarded
- **Docs** — `docs/cli.md` with the complete command index

### Changed

- `make install` installs and verifies the app+CLI pair
  (`make verify-installed`)
- `make release` no longer publishes or generates an appcast by default
  (`PUBLISH=0`, `GENERATE_APPCAST=0`)

### Fixed

- `winmux-genpatch.py` now writes a trailing newline — patches were
  rejected as corrupt by `git apply`

### CI

- New `.github/workflows/test.yml` — `swift test` + release build on
  `macos-26` (requires macOS 26 SDK / Swift ≥ 6.2)