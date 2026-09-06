# Changelog

All notable changes to this fork (tobiashochguertel/winmux) are documented
here. Changes are grouped by fork release; each entry references the
`.github/patches/` file it came from.

Upstream changes are tracked in upstream's GitHub releases — this changelog
covers fork-only modifications.

## [Unreleased] — dev.patch

### Changed (`004-restore-updater-fork-appcast.patch`)

- **Sparkle updater restored and fixed for the fork**: automatic update
  checks on again, "Check for Updates…" menu item back — but now against
  the **fork's own appcast** (`tobiashochguertel/winmux` releases),
  signed with the fork's own Ed25519 key (private key in the local login
  keychain). The upstream feed (and its bogus "1.0" item pointing at an
  old zip) can never reach fork users again.
- First release with an appcast: `make release VERSION=… GENERATE_APPCAST=1 PUBLISH=1`
  (app-only appcast entries still require `ALLOW_APP_ONLY_PROTOCOL_UPDATE=1`).

### Removed (`003-remove-sparkle-updater.patch`)

- **Sparkle updater removed from fork builds** — no automatic update
  checks, no "Check for Updates…" menu item, no upstream appcast contact.
  The fork publishes no appcast, so the updater could only offer stale or
  broken updates (e.g. upstream's bogus "1.0" item pointing at 0.5.1).

### Added (fork identity, `002-fork-identity-and-tcc-reset.patch`)

- **Own bundle ID** — `com.tobiashochguertel.winmux` (debug:
  `com.tobiashochguertel.winmux.debug`). Socket path, LaunchAgent plist,
  and diagnostic caches derive from it; no more TCC collisions with
  upstream installs.
- **TCC reset on install** — `make install` resets stale Accessibility
  grants for the fork's bundle ID (`TCC_RESET=0` to skip).

### Changed

- Sparkle automatic update checks are **disabled**; the feed points at the
  fork's releases (no more upstream "1.0" update offer).
- `startAtLogin` cleanup also removes the upstream login item.

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