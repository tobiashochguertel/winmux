# Widget Development Workflow

**Branch:** `feature/browser-widget`
**Date:** 2026-08-24
**Status:** Complete

---

## Original question

> How do we develop these kind of widgets, do we create them in `dev` or
> `dev.patch`? Or do we create a feature branch from `dev.patch`?

## Answer

It depends on whether the widget creates **new files only** or **modifies
existing upstream files**. The fork's revert-then-repatch strategy (see
[`.github/FORK-STRATEGY.md`](../../.github/FORK-STRATEGY.md)) dictates this.

---

## Branch model

```
main              ← stable, upstream release tags
 └── dev.patch    ← upstream/main + 8 custom .patch files
      ├── feature/browser-widget         (new block, new files only)
      └── feature/preview-documents      (modifies upstream files)
```

All feature branches are based on `dev.patch`. They're independent and can
be developed in parallel.

---

## Two development strategies

### Strategy A: New files only (no upstream conflicts)

**Applies to:** Browser widget (`"remotebrowser"` block)

This widget creates entirely new files:
- `emain/emain-container.ts` (new)
- `frontend/app/view/remotebrowser/*.tsx` (new)
- No existing upstream files are modified

Per the fork strategy: **"New files don't need reverting"** — they don't
exist in upstream, so the daily sync workflow will never touch them.

**Workflow:**
1. Create feature branch from `dev.patch`
2. Develop with direct commits (no `.patch` file needed)
3. Test: `npm run build:dev`, `go build ./pkg/...`
4. When stable, merge feature branch → `dev.patch`
5. Upstream sync will never conflict on these files

```bash
git checkout dev.patch
git checkout -b feature/browser-widget
# ... develop ...
git checkout dev.patch
git merge --no-ff feature/browser-widget
```

### Strategy B: Modifies upstream files (needs `.patch` file)

**Applies to:** Preview widget (enhances `"preview"` block)

This widget modifies files that already exist in upstream:

| File | In `PATCHED_FILES`? | Action |
|------|---------------------|--------|
| `frontend/app/view/preview/preview-model.tsx` | **Yes** (PR #3443) | Must be in `.patch` file |
| `frontend/app/view/preview/preview.tsx` | No | Add to `PATCHED_FILES` |
| `frontend/app/view/preview/preview-streaming.tsx` | No | Add to `PATCHED_FILES` |
| `frontend/app/view/preview/preview-pdf.tsx` | New file | Direct commit (no patch needed) |
| `frontend/app/view/preview/preview-docx.tsx` | New file | Direct commit (no patch needed) |
| `frontend/app/view/preview/preview-xlsx.tsx` | New file | Direct commit (no patch needed) |
| `frontend/app/view/preview/preview-pptx.tsx` | New file | Direct commit (no patch needed) |

Per the fork strategy: **"Never edit upstream files directly — always via
a `.patch` file"**

**Workflow:**
1. Create feature branch from `dev.patch`
2. Develop with direct commits on the feature branch
3. When stable, generate a `.patch` file from the feature branch
4. Test the patch: `git apply --check`, `npm run build:dev`, verify idempotency
5. Add modified files to `PATCHED_FILES` in the workflow
6. Commit the `.patch` file + new source files to `dev.patch`
7. Delete the feature branch

```bash
git checkout dev.patch
git checkout -b feature/preview-documents
# ... develop ...

# Generate patch (see WinMux-genpatch.py below)
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch

# Test
git apply --check .github/patches/009-preview-document-formats.patch
git apply --reverse --check .github/patches/009-preview-document-formats.patch

# Apply to dev.patch
git checkout dev.patch
git apply .github/patches/009-preview-document-formats.patch
git add .github/patches/009-preview-document-formats.patch
git add frontend/app/view/preview/preview-pdf.tsx  # new files
git add frontend/app/view/preview/preview-docx.tsx
git add frontend/app/view/preview/preview-xlsx.tsx
git add frontend/app/view/preview/preview-pptx.tsx
git commit -m "feat: integrate preview document formats via .patch"
```

---

## Why not develop directly on `dev.patch`?

You **could** for Strategy A (new files only). But feature branches are
better because:

- Keeps `dev.patch` mergeable with upstream at all times
- Allows parallel development of multiple widgets
- Easier to abandon one if it doesn't work out
- Clear separation in git history
- The daily sync workflow runs on `dev.patch` — if you have half-finished
  code there, the sync might fail or create confusing commits

Strategy B **must** go through the `.patch` file process — there's no way
around it because it modifies files that upstream also modifies.

---

## Automating `.patch` file generation

A PEP 723 script `WinMux-genpatch.py` automates generating `.patch` files
from feature branches. It:

1. Finds the merge base between the feature branch and `dev.patch`
2. Extracts only the changes to files that exist in upstream (modified files)
3. Excludes new files (those are committed directly, not via patch)
4. Writes the `.patch` file to `.github/patches/`
5. Validates the patch applies cleanly and is idempotent
6. Optionally updates `PATCHED_FILES` and `ALREADY_INTEGRATED`

**Script location:** `~/work/dev/tools/pep723-scripts/WinMux-genpatch.py`
**Docs:** [WinMux-genpatch.md](./WinMux-genpatch.md)

### Usage

```bash
# Generate a patch from a feature branch
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch

# Dry run (show what would be included, don't write)
uv run WinMux-genpatch --branch feature/preview-documents --dry-run

# Generate and validate
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate

# Generate, validate, and update PATCHED_FILES
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate --update-patched-files

# List existing patches
uv run WinMux-genpatch --list
```

### Scheduling

The script can be run manually or scheduled via cron/Forgejo Actions:

```bash
# Manual
uv run WinMux-genpatch --branch feature/preview-documents --validate

# Cron (daily at 08:00, after the upstream sync at 07:00)
0 8 * * * cd /path/to/WinMux && uv run WinMux-genpatch \
    --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate --commit
```

---

## Decision matrix

| Widget | Strategy | New files? | Modifies upstream? | `.patch` needed? | Branch |
|--------|----------|------------|---------------------|-------------------|--------|
| Browser widget | A | Yes (all) | No | No | `feature/browser-widget` |
| Preview widget | B | Yes (4 new) | Yes (3 modified) | Yes | `feature/preview-documents` |

## Rules

1. **Always branch from `dev.patch`** — not from `main` or `dev`
2. **Never edit upstream files directly on `dev.patch`** — use `.patch` files
3. **New files don't need patches** — commit them directly
4. **Test patches before committing** — `git apply --check` + build + idempotency
5. **Add modified files to `PATCHED_FILES`** — so the sync workflow reverts them before merging upstream
6. **Keep feature branches short-lived** — merge back to `dev.patch` when stable
7. **One logical change per `.patch` file** — don't combine unrelated changes
