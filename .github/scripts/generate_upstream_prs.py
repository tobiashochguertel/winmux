#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pygithub>=2.5",
#     "pyyaml>=6.0",
# ]
# ///
"""Generate .github/UPSTREAM-PRS.md from open upstream pull requests.

Fetches all open PRs via PyGithub, categorizes them by risk level,
detects file overlaps, and writes a markdown document.

Usage:
    uv run --script .github/scripts/generate_upstream_prs.py
    uv run --script .github/scripts/generate_upstream_prs.py --config .github/pr-catalog.yaml

Configuration:
    A YAML config file can control display options. See --config.
    Defaults can be overridden via CLI flags.

    Example .github/pr-catalog.yaml:
        files_display: multiline          # multiline | inline
        files_max: 0                      # 0 = show all, N = show first N
        files_show_changes: true          # show +N/-N per file
        files_link_target: pr-diff        # pr-diff | origin | none
        show_size: true                   # show total +N/-N column
        link_prs: true                    # link PR numbers to GitHub

Environment:
    GITHUB_TOKEN — GitHub token with read access to public repos.
                   In GitHub Actions, GITHUB_TOKEN is set automatically.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from github import Github

UPSTREAM_REPO = "ZimengXiong/winmux"
OUTPUT_FILE = Path(".github/UPSTREAM-PRS.md")
DEFAULT_CONFIG_FILE = Path(".github/pr-catalog.yaml")

# Files we already patch in this fork — PRs touching these get elevated risk
PATCHED_FILES = set()

# Files that are conflict-prone in upstream (frequently changed, config schemas)
CONFLICT_PRONE_FILES = set()

# PRs already integrated in this fork
ALREADY_INTEGRATED = {}

# PRs to exclude (dependabot, docs-only, etc.)
DEPENDABOT_AUTHORS = {"dependabot[bot]", "app/dependabot", "github-actions[bot]"}


# ─── Data models ─────────────────────────────────────────────────────────────


@dataclass
class FileChange:
    """A single file changed in a PR."""
    filename: str
    additions: int = 0
    deletions: int = 0

    @property
    def changes(self) -> str:
        return f"+{self.additions}/-{self.deletions}"


@dataclass
class PR:
    number: int
    title: str
    author: str
    additions: int
    deletions: int
    files: list[FileChange]
    created_at: str

    @property
    def size(self) -> str:
        return f"+{self.additions}/-{self.deletions}"

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def filenames(self) -> list[str]:
        return [f.filename for f in self.files]

    @property
    def total_changes(self) -> int:
        return self.additions + self.deletions

    @property
    def is_dependabot(self) -> bool:
        return self.author in DEPENDABOT_AUTHORS

    @property
    def is_docs_only(self) -> bool:
        return all(
            f.filename.startswith("docs/") or f.filename.endswith(".mdx") or f.filename.endswith(".md")
            for f in self.files
        )

    @property
    def touches_patched_files(self) -> bool:
        return bool(set(self.filenames) & PATCHED_FILES)

    @property
    def touches_conflict_prone(self) -> bool:
        return bool(set(self.filenames) & CONFLICT_PRONE_FILES)

    @property
    def risk(self) -> str:
        if self.is_dependabot or self.is_docs_only:
            return "N/A"
        if self.file_count == 1 and self.total_changes < 10 and not self.touches_conflict_prone:
            return "Zero"
        if self.file_count <= 2 and self.total_changes < 60 and not self.touches_patched_files and not self.touches_conflict_prone:
            return "Low"
        if self.file_count > 7 or self.total_changes > 500:
            return "High"
        return "Medium"

    @property
    def patch_fit(self) -> str:
        if self.is_dependabot or self.is_docs_only:
            return "N/A"
        if self.risk == "Zero":
            return "Excellent"
        if self.risk == "Low":
            return "Great" if self.file_count <= 2 else "Good"
        if self.risk == "Medium":
            if self.touches_patched_files:
                return "Caution — overlaps existing patch"
            return "Caution — config schema changes" if self.touches_conflict_prone else "Caution"
        return "Risky"


@dataclass
class CatalogConfig:
    """Display configuration for the PR catalog."""
    # File column options
    files_display: str = "inline"        # "multiline" | "inline"
    files_max: int = 2                   # 0 = show all, N = show first N
    files_show_changes: bool = False     # show +N/-N per file
    files_link_target: str = "none"      # "pr-diff" | "origin" | "none"
    # Table options
    show_size: bool = True               # show total +N/-N column
    link_prs: bool = True                # link PR numbers to GitHub

    @classmethod
    def from_yaml(cls, path: Path) -> CatalogConfig:
        """Load config from a YAML file."""
        import yaml
        data = yaml.safe_load(path.read_text()) or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {
            "files_display": self.files_display,
            "files_max": self.files_max,
            "files_show_changes": self.files_show_changes,
            "files_link_target": self.files_link_target,
            "show_size": self.show_size,
            "link_prs": self.link_prs,
        }


# ─── Fetching ────────────────────────────────────────────────────────────────


def fetch_prs() -> list[PR]:
    """Fetch all open PRs with file lists via PyGithub."""
    from github import Auth, Github

    token = os.environ.get("GITHUB_TOKEN", "")
    auth = Auth.Token(token) if token else None
    gh = Github(auth=auth) if auth else Github()

    repo = gh.get_repo(UPSTREAM_REPO)
    prs: list[PR] = []
    for pr in repo.get_pulls(state="open", sort="created", direction="desc"):
        files = [
            FileChange(filename=f.filename, additions=f.additions, deletions=f.deletions)
            for f in pr.get_files()
        ]
        prs.append(PR(
            number=pr.number,
            title=pr.title,
            author=pr.user.login,
            additions=pr.additions,
            deletions=pr.deletions,
            files=files,
            created_at=pr.created_at.isoformat(),
        ))
    return prs


# ─── Formatting helpers ──────────────────────────────────────────────────────


def pr_link(number: int, cfg: CatalogConfig) -> str:
    """Format a PR number as a clickable markdown link (or plain text)."""
    if cfg.link_prs:
        return f"[#{number}](https://github.com/{UPSTREAM_REPO}/pull/{number})"
    return f"#{number}"


def file_link(fc: FileChange, pr_number: int, cfg: CatalogConfig) -> str:
    """Format a single file as a link (or plain code) based on config."""
    if cfg.files_link_target == "pr-diff":
        url = f"https://github.com/{UPSTREAM_REPO}/pull/{pr_number}/files#diff-{_file_hash(fc.filename)}"
        return f"[`{fc.filename}`]({url})"
    if cfg.files_link_target == "origin":
        url = f"https://github.com/{UPSTREAM_REPO}/blob/main/{fc.filename}"
        return f"[`{fc.filename}`]({url})"
    return f"`{fc.filename}`"


def _file_hash(filename: str) -> str:
    """GitHub uses a SHA-256 hash of the file path for diff anchors."""
    import hashlib
    return hashlib.sha256(filename.encode()).hexdigest()


def fmt_files(files: list[FileChange], pr_number: int, cfg: CatalogConfig) -> str:
    """Format file list for a table cell based on config."""
    if not files:
        return "—"

    # Determine which files to show
    show = files if cfg.files_max == 0 else files[:cfg.files_max]
    remaining = len(files) - len(show)

    # Build per-file string
    parts: list[str] = []
    for fc in show:
        s = file_link(fc, pr_number, cfg)
        if cfg.files_show_changes:
            s += f" `{fc.changes}`"
        parts.append(s)

    if cfg.files_display == "multiline":
        cell = "<br>".join(parts)
        if remaining > 0:
            cell += f"<br>… _+{remaining} more_"
    else:
        cell = ", ".join(parts)
        if remaining > 0:
            cell += f", … _+{remaining} more_"

    return cell


def compute_file_overlaps(prs: list[PR]) -> dict[str, list[int]]:
    """Find files that appear in multiple PRs."""
    file_to_prs: dict[str, list[int]] = defaultdict(list)
    for pr in prs:
        if pr.is_dependabot or pr.is_docs_only:
            continue
        for fc in pr.files:
            file_to_prs[fc.filename].append(pr.number)
    return {f: sorted(nums) for f, nums in file_to_prs.items() if len(nums) > 1}


# ─── Markdown generation ─────────────────────────────────────────────────────


def _table_header(cfg: CatalogConfig, extra_cols: list[str] | None = None) -> list[str]:
    """Build a table header row based on config."""
    cols = ["PR", "Title"]
    if cfg.show_size:
        cols.append("Size")
    cols.append("Files")
    if extra_cols:
        cols.extend(extra_cols)
    sep = "|".join(["----"] * len(cols))
    return [f"| {' | '.join(cols)} |", f"|{sep}|"]


def generate_markdown(prs: list[PR], cfg: CatalogConfig) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# WinMux Upstream Pull Requests",
        "",
        f"Catalog of open pull requests from [{UPSTREAM_REPO}](https://github.com/{UPSTREAM_REPO}/pulls)",
        "evaluated for integration into the fork via the `.patch` strategy.",
        "",
        f"**Last updated:** {now}",
        f"**Total open PRs:** {len(prs)}",
        "",
        "## Legend",
        "",
        "- **Risk** — conflict risk if integrated as a `.patch` file:",
        "  - **Zero** — 1 file, <10 lines, no config/schema changes",
        "  - **Low** — 1-2 files, isolated, no overlap with `PATCHED_FILES`",
        "  - **Medium** — touches files we already patch, or touches conflict-prone files (`settingsconfig.go`, `metaconsts.go`, `gotypes.d.ts`)",
        "  - **High** — large, multi-file, touches core files or config schemas",
        "- **.patch fit** — suitability for the revert-then-repatch strategy",
        "",
        "## Already integrated",
        "",
    ]

    # Already integrated table
    cols = ["PR", "Title"]
    if cfg.show_size:
        cols.append("Size")
    cols.extend(["Files", "Branch", "Patch file"])
    sep = "|".join(["----"] * len(cols))
    lines.append(f"| {' | '.join(cols)} |")
    lines.append(f"|{sep}|")

    for num, (title, branch, patch_file) in sorted(ALREADY_INTEGRATED.items()):
        pr = next((p for p in prs if p.number == num), None)
        cells = [pr_link(num, cfg), title]
        if cfg.show_size:
            cells.append(pr.size if pr else "—")
        cells.append(fmt_files(pr.files, num, cfg) if pr else "—")
        cells.extend([f"`{branch}`", f"`{patch_file}`"])
        lines.append("| " + " | ".join(cells) + " |")

    # Filter
    active = [p for p in prs if p.number not in ALREADY_INTEGRATED and not p.is_dependabot and not p.is_docs_only]
    dependabot = [p for p in prs if p.is_dependabot]
    docs_only = [p for p in prs if p.is_docs_only and p.number not in ALREADY_INTEGRATED]

    # Tier tables
    tiers = [
        ("Tier 1 — Zero risk (pure bugfixes, tiny, single-file)", "Zero"),
        ("Tier 2 — Low risk (small, isolated)", "Low"),
        ("Tier 3 — Medium risk (overlaps or touches conflict-prone files)", "Medium"),
        ("Tier 4 — High risk (large, multi-file, features)", "High"),
    ]

    for heading, risk_level in tiers:
        tier_prs = sorted([p for p in active if p.risk == risk_level], key=lambda p: p.total_changes)
        if not tier_prs:
            continue
        lines.extend(["", f"### {heading}", ""])
        lines.extend(_table_header(cfg, extra_cols=["Risk", ".patch fit"]))
        for pr in tier_prs:
            cells = [pr_link(pr.number, cfg), pr.title]
            if cfg.show_size:
                cells.append(pr.size)
            cells.append(fmt_files(pr.files, pr.number, cfg))
            cells.extend([pr.risk, pr.patch_fit])
            lines.append("| " + " | ".join(cells) + " |")

    # Docs only
    if docs_only:
        lines.extend(["", "## Not applicable", "", "### Documentation only", ""])
        lines.extend(_table_header(cfg))
        for pr in sorted(docs_only, key=lambda p: p.number, reverse=True):
            cells = [pr_link(pr.number, cfg), pr.title]
            if cfg.show_size:
                cells.append(pr.size)
            cells.append(fmt_files(pr.files, pr.number, cfg))
            lines.append("| " + " | ".join(cells) + " |")

    # Dependabot
    if dependabot:
        lines.extend(["", "### Dependabot (auto-managed by upstream)", ""])
        cols = ["PR", "Title"]
        if cfg.show_size:
            cols.append("Size")
        sep = "|".join(["----"] * len(cols))
        lines.append(f"| {' | '.join(cols)} |")
        lines.append(f"|{sep}|")
        for pr in sorted(dependabot, key=lambda p: p.number, reverse=True):
            cells = [pr_link(pr.number, cfg), pr.title]
            if cfg.show_size:
                cells.append(pr.size)
            lines.append("| " + " | ".join(cells) + " |")

    # File overlap matrix
    overlaps = compute_file_overlaps(prs)
    if overlaps:
        lines.extend(["", "## File overlap matrix", "",
                       "Files that appear in multiple PRs — integrating one may complicate integrating another:", "",
                       "| File | PRs |", "|------|-----|"])
        for f, nums in sorted(overlaps.items(), key=lambda x: (-len(x[1]), x[0])):
            pr_links = ", ".join(pr_link(n, cfg) for n in nums)
            marker = " **(patched)**" if f in PATCHED_FILES else ""
            lines.append(f"| `{f}`{marker} | {pr_links} |")

    lines.append("")
    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args() -> tuple[CatalogConfig, Path | None]:
    """Parse CLI args and merge with config file. Returns (config, output_override)."""
    args = sys.argv[1:]
    cfg = CatalogConfig()
    output: Path | None = None
    config_file: Path | None = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--config", "-c") and i + 1 < len(args):
            config_file = Path(args[i + 1])
            i += 2
        elif arg in ("--output", "-o") and i + 1 < len(args):
            output = Path(args[i + 1])
            i += 2
        elif arg == "--files-display" and i + 1 < len(args):
            cfg.files_display = args[i + 1]
            i += 2
        elif arg == "--files-max" and i + 1 < len(args):
            cfg.files_max = int(args[i + 1])
            i += 2
        elif arg == "--files-show-changes":
            cfg.files_show_changes = True
            i += 1
        elif arg == "--no-files-changes":
            cfg.files_show_changes = False
            i += 1
        elif arg == "--files-link" and i + 1 < len(args):
            cfg.files_link_target = args[i + 1]
            i += 2
        elif arg == "--show-size":
            cfg.show_size = True
            i += 1
        elif arg == "--no-size":
            cfg.show_size = False
            i += 1
        elif arg == "--link-prs":
            cfg.link_prs = True
            i += 1
        elif arg == "--no-link-prs":
            cfg.link_prs = False
            i += 1
        elif arg in ("--help", "-h"):
            _print_help()
            sys.exit(0)
        else:
            print(f"Unknown argument: {arg}", file=sys.stderr)
            sys.exit(1)

    # Config file overrides defaults, CLI flags override config file
    if config_file and config_file.exists():
        file_cfg = CatalogConfig.from_yaml(config_file)
        # Only apply file values for keys NOT set via CLI
        # (We can't easily track which were CLI-set, so file wins for defaults,
        #  but CLI flags already overwrote cfg above — so apply file only for
        #  fields that still have their default value)
        defaults = CatalogConfig()
        if cfg.files_display == defaults.files_display:
            cfg.files_display = file_cfg.files_display
        if cfg.files_max == defaults.files_max:
            cfg.files_max = file_cfg.files_max
        if cfg.files_show_changes == defaults.files_show_changes:
            cfg.files_show_changes = file_cfg.files_show_changes
        if cfg.files_link_target == defaults.files_link_target:
            cfg.files_link_target = file_cfg.files_link_target
        if cfg.show_size == defaults.show_size:
            cfg.show_size = file_cfg.show_size
        if cfg.link_prs == defaults.link_prs:
            cfg.link_prs = file_cfg.link_prs

    return cfg, output


def _print_help() -> None:
    print(__doc__)


def main() -> int:
    cfg, output_override = _parse_args()
    output = output_override or OUTPUT_FILE

    print(f"Fetching open PRs from {UPSTREAM_REPO}...")
    prs = fetch_prs()
    print(f"  Found {len(prs)} open PRs")

    dependabot_count = sum(1 for p in prs if p.is_dependabot)
    docs_count = sum(1 for p in prs if p.is_docs_only and not p.is_dependabot)
    active_count = len(prs) - dependabot_count - docs_count
    print(f"  Active: {active_count}, Dependabot: {dependabot_count}, Docs-only: {docs_count}")

    print(f"Config: {cfg.to_dict()}")
    print(f"Generating {output}...")
    markdown = generate_markdown(prs, cfg)
    output.write_text(markdown)
    print(f"  Wrote {len(markdown)} bytes to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
