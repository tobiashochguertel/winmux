# Upstream PR Catalog

The upstream PR catalog tracks open pull requests from
[ZimengXiong/winmux](https://github.com/ZimengXiong/winmux) and evaluates
each one for integration into this fork via the `.patch` strategy described in
[`FORK-STRATEGY.md`](./FORK-STRATEGY.md).

The catalog is generated automatically by a GitHub Actions workflow and stored
as `.github/UPSTREAM-PRS.md`. A companion CLI tool (`winmux-prs`) lets you
view it from the terminal, browser, or editor.

---

## Components

| Component | Path | Purpose |
|-----------|------|---------|
| Generator script | `.github/scripts/generate_upstream_prs.py` | Fetches PRs, categorizes by risk, writes markdown |
| Config file | `.github/pr-catalog.yaml` | Controls display options |
| Workflow | `.github/workflows/update-upstream-prs.yml` | Runs the generator weekly, commits changes |
| Output | `.github/UPSTREAM-PRS.md` | The generated catalog |
| Viewer CLI | `winmux-prs` (in `~/bin/`) | Fetches and displays the catalog locally |

---

## How the catalog works

### Risk classification

Every open PR is classified into one of four risk tiers based on file count,
total line changes, and whether it touches files this fork already patches or
files that are conflict-prone in upstream:

| Tier | Criteria | .patch fit |
|------|----------|------------|
| **Zero** | 1 file, <10 lines, no config/schema files | Excellent |
| **Low** | 1-2 files, <60 lines, no overlap with patched or conflict-prone files | Great / Good |
| **Medium** | Touches patched files, conflict-prone files, or 3-7 files with <500 total changes | Caution |
| **High** | >7 files or >500 total changes | Risky |

PRs that are documentation-only or from dependabot are listed separately under
"Not applicable" and excluded from risk classification.

### .patch fit

The "fit" column indicates how suitable a PR is for the revert-then-repatch
strategy:

- **Excellent** — tiny, single-file, no schema changes; trivial to patch
- **Great / Good** — small and isolated; low conflict risk
- **Caution** — touches files we already patch (overlap) or conflict-prone config schemas
- **Risky** — large, multi-file; likely to conflict on future upstream merges

### File overlap matrix

The catalog includes a matrix showing files that appear in multiple open PRs.
Integrating one PR that touches a file may complicate integrating another PR
that touches the same file. Files this fork already patches are marked
**(patched)**.

### Already integrated PRs

PRs that have been integrated into the fork are listed at the top with their
branch and patch file name. This is maintained manually in the
`ALREADY_INTEGRATED` dict inside the generator script.

---

## Configuration

Display options are controlled via `.github/pr-catalog.yaml`. CLI flags
override config file values, which override built-in defaults.

### Config file

```yaml
# .github/pr-catalog.yaml

# File column options
files_display: inline          # inline | multiline
files_max: 2                   # 0 = show all, N = show first N
files_show_changes: false      # show +N/-N per file
files_link_target: none        # pr-diff | origin | none

# Table options
show_size: true                # show total +N/-N column
link_prs: true                 # link PR numbers to GitHub
```

### Options reference

#### `files_display`

How multiple files are arranged within a table cell.

| Value | Effect |
|-------|--------|
| `inline` | Files separated by commas on one line |
| `multiline` | Each file on its own line via `<br>` (renders as separate lines on GitHub) |

#### `files_max`

Controls how many files are shown per PR.

| Value | Effect |
|-------|--------|
| `0` | Show all files |
| `N` | Show first N files, append "… +X more" if there are more |

#### `files_show_changes`

When `true`, appends `+N/-N` after each file name showing the additions and
deletions for that specific file.

#### `files_link_target`

Controls whether file names are clickable links and where they point.

| Value | Link target |
|-------|-------------|
| `none` | No link — plain `` `filename` `` |
| `origin` | Links to `https://github.com/ZimengXiong/winmux/blob/main/<filename>` (the unmodified upstream file) |
| `pr-diff` | Links to the specific diff anchor in the PR: `https://github.com/ZimengXiong/winmux/pull/<N>/files#diff-<sha256>` |

The `pr-diff` option uses GitHub's SHA-256 hash of the file path to construct
the diff anchor URL, which jumps directly to that file's diff in the PR.

#### `show_size`

When `true`, includes a "Size" column showing total `+N/-N` for each PR.
When `false`, the column is omitted from all tables.

#### `link_prs`

When `true`, PR numbers are rendered as
`[#NNN](https://github.com/ZimengXiong/winmux/pull/NNN)` (clickable links).
When `false`, plain `#NNN` text.

### CLI flags

All options can be set via CLI flags when running the generator manually.
Flags override config file values.

```
--config <path>              Load config from YAML file
--output <path>              Write to alternate file (default: .github/UPSTREAM-PRS.md)
--files-display <mode>       inline | multiline
--files-max <N>              0 = all, N = first N
--files-show-changes         Show +N/-N per file
--no-files-changes           Hide per-file changes
--files-link <target>        pr-diff | origin | none
--show-size                  Show Size column
--no-size                    Hide Size column
--link-prs                   Link PR numbers
--no-link-prs                Plain PR numbers
--help, -h                   Show help
```

### Config priority

```
CLI flags  >  YAML config file  >  built-in defaults
```

A CLI flag explicitly set on the command line always wins. If a flag is not
set, the YAML config file value is used. If neither is provided, the built-in
default applies.

---

## Generator script

The generator is a PEP 723 inline-script at
`.github/scripts/generate_upstream_prs.py`. It uses
[PyGithub](https://pygithub.readthedocs.io/) to fetch open PRs and their file
lists from the upstream repo, then renders the catalog as markdown.

### Running locally

```bash
# With GITHUB_TOKEN for authenticated requests (higher rate limits)
GITHUB_TOKEN=$(gh auth token) uv run --script .github/scripts/generate_upstream_prs.py

# With config file
GITHUB_TOKEN=$(gh auth token) uv run --script .github/scripts/generate_upstream_prs.py --config .github/pr-catalog.yaml

# With CLI overrides
GITHUB_TOKEN=$(gh auth token) uv run --script .github/scripts/generate_upstream_prs.py \
  --files-display multiline --files-max 0 --files-show-changes --files-link pr-diff

# Write to a different file (e.g. for preview)
GITHUB_TOKEN=$(gh auth token) uv run --script .github/scripts/generate_upstream_prs.py --output /tmp/prs.md
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | No | GitHub token for authenticated API requests. Without it, unauthenticated requests are used (60 req/hr limit). In GitHub Actions, this is set automatically. |

### Dependencies

Declared in the PEP 723 script header:

- `pygithub>=2.5` — GitHub API client
- `pyyaml>=6.0` — YAML config file parsing

Installed automatically by `uv run --script`.

### Internal data

The script maintains three hardcoded data structures that need manual updates
when patches are added or removed:

- **`PATCHED_FILES`** — set of file paths this fork patches. PRs touching
  these get elevated risk and a "Caution — overlaps existing patch" fit rating.
- **`CONFLICT_PRONE_FILES`** — set of upstream files that are frequently
  changed or hold config schemas. PRs touching these get "Caution — config
  schema changes".
- **`ALREADY_INTEGRATED`** — dict mapping PR numbers to
  `(title, branch, patch_file)` tuples. These appear in the "Already
  integrated" table at the top of the catalog.

When you add a new patch to the fork, update all three in the script.

---

## Workflow

The `update-upstream-prs.yml` workflow runs the generator and commits changes
to `.github/UPSTREAM-PRS.md`.

### Schedule

- **Weekly**: Every Monday at 06:00 UTC
- **Manual**: Via `gh workflow run` or the GitHub Actions UI

### What it does

1. Checks out the repo
2. Installs `uv`
3. Runs the generator with `--config .github/pr-catalog.yaml`
4. Commits and pushes if `.github/UPSTREAM-PRS.md` changed
5. Skips commit if nothing changed ("No changes — catalog is up to date")

### Triggering manually

```bash
# From the CLI
gh workflow run update-upstream-prs.yml --repo tobiashochguertel/WinMux --ref main

# Check the run status
gh run list --repo tobiashochguertel/WinMux --workflow update-upstream-prs.yml --limit 3
```

### Permissions

The workflow uses `permissions: contents: write` and the automatically-provided
`GITHUB_TOKEN` (no secret needed). The token is passed to the generator via
`env: GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}`.

---

## Viewer CLI (`winmux-prs`)

A PEP 723 script installed via `scriptmgr` to `~/bin/winmux-prs`. Fetches the
catalog from GitHub and displays it in the terminal, browser, or editor.

### Installation

The script lives at `~/dotfiles/tools/pep723-scripts/winmux-prs.py` and is
symlinked into `~/bin/` by `scriptmgr`:

```bash
cd ~/dotfiles/tools/pep723-scripts
scriptmgr install
```

### Usage

```bash
winmux-prs                         # show in terminal (rich markdown tables)
winmux-prs --browser               # open GitHub-rendered page in browser
winmux-prs --editor                # open raw markdown in $EDITOR
winmux-prs --raw                   # print raw markdown to stdout (for piping)
winmux-prs --regenerate            # regenerate locally, then show in terminal
winmux-prs --regenerate --browser  # regenerate, then open in browser
winmux-prs --branch dev.patch      # fetch from dev.patch instead of main
winmux-prs --repo user/repo        # fetch from a different fork
```

### Options

| Flag | Short | Description |
|------|-------|-------------|
| `--browser` | `-b` | Open the GitHub page directly in the default browser |
| `--editor` | `-e` | Open raw markdown in `$EDITOR` (defaults to `less`) |
| `--raw` | | Print raw markdown to stdout — useful for piping to other tools |
| `--regenerate` | `-r` | Run the generator script locally before fetching. Requires the WinMux fork at `~/work/dev/tools/WinMux` |
| `--repo` | | GitHub repo in `owner/name` format (default: `tobiashochguertel/WinMux`) |
| `--branch` | | Branch to fetch from (default: `main`) |

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WINMUX_PRS_REPO` | `tobiashochguertel/WinMux` | Default repo |
| `WINMUX_PRS_BRANCH` | `main` | Default branch |
| `GITHUB_TOKEN` | _(unset)_ | GitHub token for higher API rate limits. Optional — works without for public repos. |
| `EDITOR` | `less` | Editor for `--editor` mode |

### How `--browser` works

The `--browser` flag opens
`https://github.com/<repo>/blob/<branch>/.github/UPSTREAM-PRS.md` directly.
GitHub renders the markdown with proper table formatting, syntax highlighting,
and clickable links. No local HTML rendering is needed.

### How `--regenerate` works

The `--regenerate` flag runs the generator script locally
(`uv run --script .github/scripts/generate_upstream_prs.py`) in the WinMux
fork directory, then fetches the updated file from GitHub. This is useful for
previewing changes after updating `ALREADY_INTEGRATED` or `PATCHED_FILES`
without waiting for the weekly workflow.

---

## Common tasks

### Change the display format

Edit `.github/pr-catalog.yaml` and commit. The next workflow run will use the
new settings. To preview locally:

```bash
GITHUB_TOKEN=$(gh auth token) uv run --script .github/scripts/generate_upstream_prs.py \
  --config .github/pr-catalog.yaml --output /tmp/preview.md
cat /tmp/preview.md
```

### Mark a PR as integrated

After integrating a PR into the fork via a `.patch` file:

1. Open `.github/scripts/generate_upstream_prs.py`
2. Add an entry to `ALREADY_INTEGRATED`:
   ```python
   ALREADY_INTEGRATED = {
       3429: ("fix: stop a de-focusing block from re-grabbing focus", "dev.patch", "003-focus-fix.patch"),
       3420: ("Fix bookmark typeahead not rendering suggestions", "dev.patch", "002-bookmark-typeahead-fix.patch"),
       1234: ("your PR title", "dev.patch", "004-your-patch.patch"),  # new entry
   }
   ```
3. If the PR touches new files, add them to `PATCHED_FILES`
4. Commit and push. The next workflow run will move the PR to the "Already
   integrated" table.

### Add a new conflict-prone file

If upstream frequently changes a file that causes merge conflicts:

1. Open `.github/scripts/generate_upstream_prs.py`
2. Add the file path to `CONFLICT_PRONE_FILES`
3. PRs touching that file will now be classified as "Caution — config schema
   changes" in the catalog

### View the catalog from a different branch

```bash
winmux-prs --branch dev.patch
winmux-prs --branch dev.patch --browser
```
