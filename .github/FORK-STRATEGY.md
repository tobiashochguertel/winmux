# Fork Maintenance Strategy

This fork of [ZimengXiong/winmux](https://github.com/ZimengXiong/winmux) is kept
mergeable with upstream using a **revert-then-repatch** strategy.

## Branch model

| Branch | Tracks | Purpose |
|--------|--------|---------|
| `main` | Latest upstream release tag (e.g. `v0.5.3`) | Stable — well-tested patches only |
| `dev.patch` | `upstream/main` (latest development) | Unstable — experimental patches welcome |

## Upstream PR catalog

An automated catalog of open upstream PRs is maintained at
[`.github/UPSTREAM-PRS.md`](./UPSTREAM-PRS.md) — see
[`PR-CATALOG.md`](./PR-CATALOG.md) for full documentation of the generator and
config options.

## What lives where

### Tier 1: User config (NOT in this repo)

User-level config lives in `~/.config/winmux/winmux.toml` and is managed via
dotfiles.

**Never commit this to the fork.** It's user-specific and would conflict.

### Tier 2: Source patches (in this repo)

Actual changes to upstream source files. These are the only things that risk
merge conflicts. Each patch has:

1. **A `.patch` file** in `.github/patches/` (named `NNN-description.patch`)
2. **An entry in `PATCHED_FILES`** in the sync workflow env var (modified files only — new files don't need listing)
3. **An entry in `ALREADY_INTEGRATED`** in `.github/scripts/generate_upstream_prs.py` (for the PR catalog)

Patches are applied by `.github/scripts/apply_patches.sh`, which loops over
all `.patch` files in `.github/patches/` in alphabetical order.

There are no patches yet — this fork currently tracks upstream cleanly.

## How the sync works

The `sync-upstream-and-fix.yml` workflow runs daily at 07:00 UTC (or manually).
It syncs both branches in parallel — `main` from the latest upstream release
tag, `dev.patch` from `upstream/main`.

### The revert-then-repatch sequence

For each branch, the workflow executes these steps:

```bash
# 1. Fetch upstream
git remote add upstream https://github.com/ZimengXiong/winmux.git
git fetch upstream --tags --quiet

# 2. Determine what to merge
#    main:       latest upstream release tag (e.g. v0.5.3)
#    dev.patch:  upstream/main

# 3. Skip if already up to date
git merge-base --is-ancestor "$UPSTREAM_SHA" HEAD  # → nothing to do

# 4. Revert all PATCHED_FILES to upstream's version, then commit
#    This removes our custom changes from the working tree so the merge
#    won't conflict on those files.
.github/scripts/revert_patched_files.sh "$UPSTREAM_SHA" "$MERGE_REF"
#    → git checkout "$UPSTREAM_SHA" -- <each patched file>
#    → git commit -m "chore: revert patched files to upstream …"

# 5. Merge upstream (normal merge, no strategy override)
git merge "$MERGE_REF" --no-edit -m "chore: merge upstream …"
#    If this conflicts on non-patched files → FAIL LOUDLY (merge --abort, exit 1)

# 6. Re-apply all patches via apply_patches.sh
.github/scripts/apply_patches.sh
#    For each .github/patches/*.patch:
#      - If git apply --reverse --check passes → already applied, skip
#      - If git apply --check passes → git apply, continue
#      - Otherwise → FAIL LOUDLY (exit 1)

# 7. Commit the re-applied patches
git add -A
git commit -m "fix: re-apply custom patches after upstream merge …"

# 8. Push
git push origin <branch>
```

### Why revert-then-repatch instead of `--strategy-option=theirs`?

`--strategy-option=theirs` silently lets upstream overwrite custom patches.
The revert-then-repatch approach:

- **Guarantees patches are always re-applied** on the latest upstream code
- **Fails loudly** if upstream changed the surrounding code (`git apply` fails)
- **Fails loudly** if there are conflicts on files we don't patch
- **Never silently drops** a custom change

### Helper scripts

| Script | Purpose |
|--------|---------|
| `.github/scripts/revert_patched_files.sh` | Checks out each `PATCHED_FILES` entry from the upstream SHA, commits the revert |
| `.github/scripts/apply_patches.sh` | Loops over `.github/patches/*.patch`, applies each with idempotency check |
| `.github/scripts/winmux-genpatch.py` | Generates `.patch` files from feature branches, updates `PATCHED_FILES` |
| `.github/scripts/validate-patches.py` | Validates all `.patch` files (applies cleanly, idempotent, listed in `PATCHED_FILES`) |

## Adding a new patch

### 1. Find the PR and generate the `.patch` file

```bash
# Fetch the PR branch
git remote add upstream https://github.com/ZimengXiong/winmux.git  # if not already present
git fetch upstream pull/<PR_NUMBER>/head:pr-<PR_NUMBER>

# Find the merge base (the commit the PR was based on)
MERGE_BASE=$(git merge-base pr-<PR_NUMBER> upstream/main)

# Generate the patch
git diff "$MERGE_BASE"..pr-<PR_NUMBER> > .github/patches/NNN-description.patch
```

Or use the genpatch tool from a feature branch:

```bash
.github/scripts/winmux-genpatch.py generate \
    --branch feature/my-change \
    --output .github/patches/NNN-description.patch \
    --validate --update-patched-files
```

### 2. Test the patch applies cleanly

```bash
# Dry-run
git apply --check .github/patches/NNN-description.patch

# Apply for real
git apply .github/patches/NNN-description.patch

# Verify the build
swift build                      # build all products
swift test                       # run tests

# Verify idempotency (reverse check should pass)
git apply --reverse --check .github/patches/NNN-description.patch

# Verify apply_patches.sh works with the new patch
.github/scripts/apply_patches.sh
```

### 3. Add modified files to `PATCHED_FILES`

In `.github/workflows/sync-upstream-and-fix.yml`, add each **modified** file
(not new files — those don't exist in upstream and don't need reverting) to
the `PATCHED_FILES` env var:

```yaml
env:
  PATCHED_FILES: |
    Sources/AppBundle/...   # ← add each modified file here
```

### 4. Register the PR in the catalog

In `.github/scripts/generate_upstream_prs.py`, add an entry to
`ALREADY_INTEGRATED`:

```python
ALREADY_INTEGRATED = {
    ...
    <PR_NUMBER>: ("PR title", "dev.patch", "NNN-description.patch"),
}
```

If the PR touches files that are frequently changed in upstream or hold config
schemas, also add them to `CONFLICT_PRONE_FILES`.

### 5. Commit and push

```bash
git add -A
git commit -m "feat: integrate PR #<NNN> <description> via .patch"
git push origin dev.patch
```

## Rules

- **Never edit upstream files directly** — always via a `.patch` file
- **Never use `--strategy-option=theirs`** — it silently drops changes
- **Keep patches minimal** — one logical change per `.patch` file
- **Name patches with zero-padded numbers** — `NNN-description.patch` (applied in alphabetical order)
- **Only list modified files in `PATCHED_FILES`** — new files don't need reverting
- **Test locally** before pushing: `git apply --check`, `swift build`, `swift test`
- **Verify idempotency** — `git apply --reverse --check` must pass (so `apply_patches.sh` can detect already-applied patches)