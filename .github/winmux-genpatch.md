# WinMux-genpatch — Generate `.patch` files from feature branches

**Script:** `WinMux-genpatch.py`
**Location:** `~/work/dev/tools/pep723-scripts/WinMux-genpatch.py`
**Type:** PEP 723 inline script (run with `uv run`)

---

## Purpose

Automates generating `.patch` files for the WinMux fork's revert-then-repatch
strategy. Given a feature branch, it:

1. Finds the merge base between the feature branch and `dev.patch`
2. Extracts changes to files that **already exist in upstream** (modified files)
3. **Excludes new files** (those are committed directly to `dev.patch`, not via patch)
4. Writes the `.patch` file to `.github/patches/`
5. Optionally validates the patch applies cleanly and is idempotent
6. Optionally updates `PATCHED_FILES` in the workflow and `ALREADY_INTEGRATED` in `generate_upstream_prs.py`
7. Optionally commits the patch + new files to `dev.patch`

---

## Usage

```bash
# Generate a patch from a feature branch
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch

# Dry run (show what would be included, don't write)
uv run WinMux-genpatch --branch feature/preview-documents --dry-run

# Generate and validate (apply check + reverse check)
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate

# Generate, validate, and update PATCHED_FILES
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate --update-patched-files

# Generate, validate, update PATCHED_FILES, and commit to dev.patch
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate --update-patched-files --commit

# List existing patches
uv run WinMux-genpatch --list

# Show which files in a feature branch are modified vs new
uv run WinMux-genpatch --branch feature/preview-documents --analyze
```

---

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--branch` | `str` | required | Feature branch to generate patch from |
| `--output` | `Path` | auto | Output `.patch` file path (default: `.github/patches/NNN-<branch>.patch`) |
| `--base-branch` | `str` | `dev.patch` | Base branch to diff against |
| `--dry-run` | `flag` | `false` | Show what would be included without writing |
| `--validate` | `flag` | `false` | Run `git apply --check` and `git apply --reverse --check` |
| `--update-patched-files` | `flag` | `false` | Add modified files to `PATCHED_FILES` in workflow |
| `--commit` | `flag` | `false` | Commit patch + new files to base branch |
| `--list` | `flag` | `false` | List existing patches in `.github/patches/` |
| `--analyze` | `flag` | `false` | Show modified vs new files in the feature branch |
| `--repo` | `Path` | `cwd` | Path to the WinMux repo |
| `--verbose` | `flag` | `false` | Show detailed output |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WINMUX_GENPATCH_REPO` | `cwd` | Path to the WinMux repo |
| `WINMUX_GENPATCH_BASE` | `dev.patch` | Base branch |

---

## How it works

### Step 1: Find merge base

```bash
git merge-base dev.patch feature/preview-documents
# → <commit-sha>  (the point where the feature branch diverged)
```

### Step 2: Identify modified vs new files

```bash
# All changed files
git diff --name-only <merge-base>..feature/preview-documents

# For each file, check if it exists in dev.patch at the merge base
git cat-file -e <merge-base>:<file>  # exits 0 if exists, 1 if new
```

- **Modified files** (exist in upstream) → included in `.patch` file
- **New files** (don't exist in upstream) → excluded from `.patch`, committed directly

### Step 3: Generate patch (modified files only)

```bash
git diff <merge-base>..feature/preview-documents -- <modified-file-1> <modified-file-2> ... \
    > .github/patches/009-preview-document-formats.patch
```

### Step 4: Validate (if `--validate`)

```bash
# Check it applies cleanly
git apply --check .github/patches/009-preview-document-formats.patch

# Check idempotency (reverse should also apply)
git apply --reverse --check .github/patches/009-preview-document-formats.patch
```

### Step 5: Update PATCHED_FILES (if `--update-patched-files`)

Parses `.github/workflows/sync-upstream-and-fix.yml` and adds any modified
files that aren't already in the `PATCHED_FILES` list.

### Step 6: Commit (if `--commit`)

```bash
git checkout dev.patch
git apply .github/patches/009-preview-document-formats.patch
git add .github/patches/009-preview-document-formats.patch
git add <new-files-from-feature-branch>
git commit -m "feat: integrate <description> via .patch"
```

---

## Scheduling

### Manual

```bash
cd /path/to/WinMux
uv run WinMux-genpatch --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate --update-patched-files --commit
```

### Cron (daily after upstream sync)

The upstream sync runs at 07:00 UTC. Run genpatch at 08:00 to generate
patches from any feature branches that have new commits:

```cron
# Daily at 08:00 UTC — generate patches from active feature branches
0 8 * * * cd /path/to/WinMux && uv run WinMux-genpatch \
    --branch feature/preview-documents \
    --output .github/patches/009-preview-document-formats.patch \
    --validate --update-patched-files --commit \
    >> /var/log/WinMux-genpatch.log 2>&1
```

### Forgejo Actions workflow

```yaml
# .github/workflows/generate-patches.yml
name: Generate patches from feature branches

on:
  schedule:
    - cron: '0 8 * * *'  # Daily at 08:00 UTC
  workflow_dispatch:      # Manual trigger

jobs:
  genpatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for merge-base
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install uv
      - run: |
          uv run WinMux-genpatch \
            --branch feature/preview-documents \
            --output .github/patches/009-preview-document-formats.patch \
            --validate --update-patched-files --commit
      - run: git push origin dev.patch
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Feature branch not found |
| 2 | Merge base not found (branch not based on `dev.patch`?) |
| 3 | Patch validation failed (doesn't apply cleanly) |
| 4 | Idempotency check failed (reverse apply failed) |
| 5 | No changes to patch (feature branch has no modified files) |
| 6 | `PATCHED_FILES` update failed (workflow file parse error) |
