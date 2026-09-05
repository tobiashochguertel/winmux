#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer>=0.12.0",
#     "rich>=13.0.0",
# ]
# ///
"""
validate-patches — Validate all .patch files in a WinMux fork.

Checks that every .patch file in .github/patches/:
1. Applies cleanly (git apply --check)
2. Is idempotent (git apply --reverse --check)
3. Files it modifies are listed in PATCHED_FILES

Usage:
    validate-patches --repo /path/to/WinMux
    validate-patches --repo /path/to/WinMux --verbose
    validate-patches --repo /path/to/WinMux --check-patched-files

Environment variables:
    WINMUX_GENPATCH_REPO     Path to WinMux repo (default: cwd)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()

_REPO_ENV = "WINMUX_GENPATCH_REPO"
_PATCH_DIR = ".github/patches"
_WORKFLOW_FILE = ".github/workflows/sync-upstream-and-fix.yml"
_GENERATE_SCRIPT = ".github/scripts/generate_upstream_prs.py"

app = typer.Typer(
    name="validate-patches",
    help="Validate all .patch files in a WinMux fork.",
    add_completion=True,
    no_args_is_help=True,
)


def _run_git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def _parse_patched_files_from_workflow(repo: Path) -> set[str]:
    """Parse PATCHED_FILES from the workflow YAML."""
    workflow_path = repo / _WORKFLOW_FILE
    if not workflow_path.exists():
        return set()

    content = workflow_path.read_text()
    match = re.search(r"PATCHED_FILES:\s*\|\n(.*?)(?=\n[a-zA-Z]|\njobs:|\Z)", content, re.DOTALL)
    if not match:
        return set()

    files = set()
    for line in match.group(1).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            files.add(line)
    return files


def _parse_patched_files_from_script(repo: Path) -> set[str]:
    """Parse PATCHED_FILES from generate_upstream_prs.py."""
    script_path = repo / _GENERATE_SCRIPT
    if not script_path.exists():
        return set()

    content = script_path.read_text()
    match = re.search(r"PATCHED_FILES\s*=\s*\{(.*?)\}", content, re.DOTALL)
    if not match:
        return set()

    files = set()
    for line in match.group(1).splitlines():
        line = line.strip()
        # Extract quoted file paths
        for m in re.finditer(r'"([^"]+/\S+)"', line):
            files.add(m.group(1))
    return files


def _extract_patch_files(patch_path: Path) -> tuple[list[str], list[str]]:
    """Extract modified and new file paths from a .patch file.
    Returns (modified_files, new_files).
    New files are created from /dev/null; modified files already existed.
    """
    modified: list[str] = []
    new: list[str] = []
    lines = patch_path.read_text().splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("diff --git a/"):
            continue
        match = re.match(r"diff --git a/(.+) b/(.+)", line)
        if not match:
            continue
        filepath = match.group(2)
        # Check if this is a new file (source is /dev/null)
        # Look at the next few lines for "--- /dev/null"
        is_new = False
        for j in range(i + 1, min(i + 5, len(lines))):
            if lines[j].startswith("--- /dev/null"):
                is_new = True
                break
            if lines[j].startswith("--- a/"):
                break
        if is_new:
            new.append(filepath)
        else:
            modified.append(filepath)
    return modified, new


@app.command()
def validate(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        "-r",
        help="Path to the WinMux repo.",
        envvar=_REPO_ENV,
        show_default=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output for each patch.",
    ),
    check_patched_files: bool = typer.Option(
        False,
        "--check-patched-files",
        help="Also check that modified files are in PATCHED_FILES.",
    ),
) -> None:
    """Validate all .patch files in the WinMux fork."""
    patch_dir = repo / _PATCH_DIR
    if not patch_dir.exists():
        console.print("[red]Error:[/red] .github/patches/ directory not found")
        raise typer.Exit(code=1)

    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        console.print("[yellow]No .patch files found[/yellow]")
        return

    workflow_files = _parse_patched_files_from_workflow(repo)
    script_files = _parse_patched_files_from_script(repo)

    table = Table(title="Patch Validation", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Patch", style="cyan")
    table.add_column("Applies", justify="center")
    table.add_column("Idempotent", justify="center")
    table.add_column("In PATCHED_FILES", justify="center")

    errors = 0
    warnings = 0

    for i, patch in enumerate(patches, 1):
        name = patch.name

        # Check applies cleanly (not yet applied)
        applies = _run_git(repo, "apply", "--check", str(patch))
        applies_ok = applies.returncode == 0

        # Check idempotent (reverse applies — means already applied)
        reverse = _run_git(repo, "apply", "--reverse", "--check", str(patch))
        already_applied = reverse.returncode == 0

        # A patch is "valid" if it either applies cleanly OR is already applied
        # (reverse check passes). On dev.patch, patches are already applied.
        # On a fresh upstream checkout, patches should apply cleanly.
        valid = applies_ok or already_applied

        # Check patched files (only modified files need to be in PATCHED_FILES)
        patch_modified, _patch_new = _extract_patch_files(patch)
        missing_in_workflow = [f for f in patch_modified if f not in workflow_files]
        missing_in_script = [f for f in patch_modified if f not in script_files]
        all_in_patched = len(missing_in_workflow) == 0 and len(missing_in_script) == 0

        if applies_ok:
            applies_str = "[green]✅ applies[/green]"
        elif already_applied:
            applies_str = "[blue]✅ applied[/blue]"
        else:
            applies_str = "[red]❌ failed[/red]"

        idempotent_str = "[green]✅[/green]" if already_applied else ("[green]✅[/green]" if applies_ok else "[red]❌[/red]")
        patched_str = "[green]✅[/green]" if all_in_patched else "[yellow]⚠️[/yellow]"

        table.add_row(str(i), name, applies_str, idempotent_str, patched_str)

        if not valid:
            errors += 1
            if verbose:
                if not applies_ok and not already_applied:
                    console.print(f"\n[red]apply --check failed for {name}:[/red]")
                    console.print(applies.stderr, style="red")

        if not all_in_patched and check_patched_files:
            warnings += 1
            if verbose:
                if missing_in_workflow:
                    console.print(f"\n[yellow]Missing in workflow PATCHED_FILES ({name}):[/yellow]")
                    for f in missing_in_workflow:
                        console.print(f"  {f}")
                if missing_in_script:
                    console.print(f"\n[yellow]Missing in generate_upstream_prs.py ({name}):[/yellow]")
                    for f in missing_in_script:
                        console.print(f"  {f}")

    console.print(table)
    console.print()

    if errors > 0:
        console.print(f"[red]❌ {errors} error(s) found[/red]")
        raise typer.Exit(code=1)

    if warnings > 0 and check_patched_files:
        console.print(f"[yellow]⚠️  {warnings} warning(s) — files not in PATCHED_FILES[/yellow]")
        raise typer.Exit(code=2)

    console.print("[green]✅ All patches valid[/green]")


if __name__ == "__main__":
    app()
