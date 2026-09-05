#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer>=0.12.0",
#     "rich>=13.0.0",
#     "pyyaml>=6.0",
# ]
# ///
"""
winmux-genpatch — Generate .patch files from feature branches for the
WinMux fork's revert-then-repatch strategy.

Given a feature branch, extracts changes to files that already exist in
upstream (modified files) and writes them as a .patch file. New files
(those not in upstream) are excluded — they're committed directly to
dev.patch, not via patch.

Usage:
    winmux-genpatch --branch feature/preview-documents \\
        --output .github/patches/009-preview-document-formats.patch

    winmux-genpatch --branch feature/preview-documents --dry-run

    winmux-genpatch --branch feature/preview-documents \\
        --output .github/patches/009-preview-document-formats.patch \\
        --validate --update-patched-files --commit

    winmux-genpatch --list

    winmux-genpatch --branch feature/preview-documents --analyze

Environment variables:
    WINMUX_GENPATCH_REPO     Path to WinMux repo (default: cwd)
    WINMUX_GENPATCH_BASE     Base branch (default: dev.patch)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_REPO_ENV = "WINMUX_GENPATCH_REPO"
_BASE_ENV = "WINMUX_GENPATCH_BASE"
_DEFAULT_BASE = "dev.patch"
_PATCH_DIR = ".github/patches"
_WORKFLOW_FILE = ".github/workflows/sync-upstream-and-fix.yml"
_GENERATE_SCRIPT = ".github/scripts/generate_upstream_prs.py"

app = typer.Typer(
    name="winmux-genpatch",
    help="Generate .patch files from feature branches for the WinMux fork.",
    add_completion=True,
    no_args_is_help=True,
)


def _run_git(repo: Path, *args: str, capture: bool = True, check: bool = True) -> str:
    """Run a git command in the repo and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        console.print(f"[red]git error:[/red] {' '.join(args)}")
        console.print(result.stderr, style="red")
        raise typer.Exit(code=1)
    return result.stdout.strip()


def _run_git_raw(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess (for exit code checks)."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _get_merge_base(repo: Path, base: str, branch: str) -> str:
    """Find the merge base between base and branch."""
    result = _run_git_raw(repo, "merge-base", base, branch, check=False)
    if result.returncode != 0:
        console.print(f"[red]Error:[/red] Cannot find merge-base between '{base}' and '{branch}'")
        console.print(f"[dim]Is '{branch}' based on '{base}'?[/dim]")
        raise typer.Exit(code=2)
    return result.stdout.strip()


def _get_changed_files(repo: Path, merge_base: str, branch: str) -> list[str]:
    """Get all files changed between merge_base and branch."""
    output = _run_git(repo, "diff", "--name-only", f"{merge_base}..{branch}")
    if not output:
        return []
    return [f for f in output.splitlines() if f.strip()]


def _file_exists_at_ref(repo: Path, ref: str, filepath: str) -> bool:
    """Check if a file exists at a given git ref."""
    result = _run_git_raw(repo, "cat-file", "-e", f"{ref}:{filepath}", check=False)
    return result.returncode == 0


def _classify_files(repo: Path, merge_base: str, files: list[str]) -> tuple[list[str], list[str]]:
    """Split files into (modified, new) based on whether they exist at merge_base."""
    modified: list[str] = []
    new: list[str] = []
    for f in files:
        if _file_exists_at_ref(repo, merge_base, f):
            modified.append(f)
        else:
            new.append(f)
    return modified, new


def _generate_patch(repo: Path, merge_base: str, branch: str, modified_files: list[str]) -> str:
    """Generate the patch content for modified files only."""
    if not modified_files:
        return ""
    output = _run_git(repo, "diff", f"{merge_base}..{branch}", "--", *modified_files)
    return output


def _validate_patch(repo: Path, patch_path: Path) -> tuple[bool, bool]:
    """Validate patch applies cleanly and is idempotent.
    Returns (applies_cleanly, is_idempotent).
    """
    applies = _run_git_raw(repo, "apply", "--check", str(patch_path), check=False)
    applies_clean = applies.returncode == 0

    reverse = _run_git_raw(repo, "apply", "--reverse", "--check", str(patch_path), check=False)
    is_idempotent = reverse.returncode == 0

    return applies_clean, is_idempotent


def _parse_patched_files(repo: Path) -> list[str]:
    """Parse PATCHED_FILES from the workflow YAML."""
    workflow_path = repo / _WORKFLOW_FILE
    if not workflow_path.exists():
        console.print(f"[yellow]Warning:[/yellow] {_WORKFLOW_FILE} not found")
        return []

    content = workflow_path.read_text()
    # Extract the PATCHED_FILES block from the env section
    match = re.search(r"PATCHED_FILES:\s*\|\n(.*?)(?=\n[a-zA-Z]|\njobs:|\Z)", content, re.DOTALL)
    if not match:
        console.print("[yellow]Warning:[/yellow] PATCHED_FILES block not found in workflow")
        return []

    block = match.group(1)
    files = []
    for line in block.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            files.append(line)
    return files


def _update_patched_files(repo: Path, new_files: list[str]) -> bool:
    """Add new files to PATCHED_FILES in the workflow YAML.
    Returns True if any files were added.
    """
    if not new_files:
        return False

    workflow_path = repo / _WORKFLOW_FILE
    if not workflow_path.exists():
        console.print(f"[red]Error:[/red] {_WORKFLOW_FILE} not found")
        raise typer.Exit(code=6)

    content = workflow_path.read_text()
    existing = set(_parse_patched_files(repo))
    to_add = [f for f in new_files if f not in existing]
    if not to_add:
        console.print("[green]All modified files already in PATCHED_FILES[/green]")
        return False

    # Find the PATCHED_FILES block and append
    lines = content.splitlines()
    patched_section_start = None
    patched_section_end = None
    for i, line in enumerate(lines):
        if line.strip().startswith("PATCHED_FILES:"):
            patched_section_start = i + 1
        elif patched_section_start is not None and line and not line.startswith(" ") and not line.startswith("#"):
            patched_section_end = i
            break

    if patched_section_start is None:
        console.print("[red]Error:[/red] Could not locate PATCHED_FILES section")
        raise typer.Exit(code=6)

    if patched_section_end is None:
        patched_section_end = len(lines)

    # Insert new files before the end of the section
    new_lines = []
    for f in sorted(to_add):
        new_lines.append(f"    {f}")

    lines = lines[:patched_section_end] + new_lines + lines[patched_section_end:]
    workflow_path.write_text("\n".join(lines) + "\n")

    console.print(f"[green]Added {len(to_add)} file(s) to PATCHED_FILES:[/green]")
    for f in sorted(to_add):
        console.print(f"  [cyan]{f}[/cyan]")
    return True


def _list_patches(repo: Path) -> None:
    """List existing patches in .github/patches/."""
    patch_dir = repo / _PATCH_DIR
    if not patch_dir.exists():
        console.print("[yellow]No .github/patches/ directory found[/yellow]")
        return

    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        console.print("[yellow]No .patch files found[/yellow]")
        return

    table = Table(title="Existing Patches", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Patch File", style="cyan")
    table.add_column("Size", justify="right", style="green")

    for i, p in enumerate(patches, 1):
        size = p.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
        table.add_row(str(i), p.name, size_str)

    console.print(table)


def _analyze_branch(repo: Path, base: str, branch: str) -> None:
    """Show modified vs new files in a feature branch."""
    merge_base = _get_merge_base(repo, base, branch)
    files = _get_changed_files(repo, merge_base, branch)
    if not files:
        console.print("[yellow]No changes in feature branch[/yellow]")
        return

    modified, new = _classify_files(repo, merge_base, files)

    console.print(f"\n[bold]Branch:[/bold] {branch}")
    console.print(f"[bold]Base:[/bold] {base} (merge-base: {merge_base[:8]})")
    console.print()

    table = Table(title="File Classification", show_header=True, header_style="bold cyan")
    table.add_column("Type", style="bold")
    table.add_column("File", style="cyan")
    table.add_column("In PATCHED_FILES?", style="yellow")

    patched_files = set(_parse_patched_files(repo))

    for f in sorted(modified):
        in_patched = "[green]yes[/green]" if f in patched_files else "[red]no[/red]"
        table.add_row("modified", f, in_patched)

    for f in sorted(new):
        table.add_row("new", f, "[dim]n/a[/dim]")

    console.print(table)
    console.print()
    console.print(f"[bold]Summary:[/bold] {len(modified)} modified, {len(new)} new")
    console.print()
    console.print("[dim]Modified files go into the .patch file.[/dim]")
    console.print("[dim]New files are committed directly to dev.patch.[/dim]")


@app.command()
def generate(
    branch: str = typer.Option(
        ...,
        "--branch",
        "-b",
        help="Feature branch to generate patch from.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .patch file path. Default: .github/patches/NNN-<branch>.patch",
    ),
    base_branch: str = typer.Option(
        _DEFAULT_BASE,
        "--base",
        help="Base branch to diff against.",
        envvar=_BASE_ENV,
        show_default=True,
    ),
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        "-r",
        help="Path to the WinMux repo.",
        envvar=_REPO_ENV,
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be included without writing.",
    ),
    validate: bool = typer.Option(
        False,
        "--validate",
        help="Run git apply --check and git apply --reverse --check.",
    ),
    update_patched_files: bool = typer.Option(
        False,
        "--update-patched-files",
        help="Add modified files to PATCHED_FILES in the workflow.",
    ),
    commit: bool = typer.Option(
        False,
        "--commit",
        help="Commit patch + new files to base branch.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed output.",
    ),
) -> None:
    """Generate a .patch file from a feature branch."""
    # Verify branch exists
    branch_check = _run_git_raw(repo, "rev-parse", "--verify", branch, check=False)
    if branch_check.returncode != 0:
        console.print(f"[red]Error:[/red] Branch '{branch}' not found")
        raise typer.Exit(code=1)

    # Find merge base
    merge_base = _get_merge_base(repo, base_branch, branch)
    if verbose:
        console.print(f"[dim]Merge base: {merge_base}[/dim]")

    # Get changed files
    files = _get_changed_files(repo, merge_base, branch)
    if not files:
        console.print("[yellow]No changes in feature branch[/yellow]")
        raise typer.Exit(code=5)

    # Classify files
    modified, new = _classify_files(repo, merge_base, files)

    if verbose or dry_run:
        console.print()
        console.print(f"[bold]Modified files[/bold] ({len(modified)}):")
        for f in modified:
            console.print(f"  [cyan]{f}[/cyan]")
        console.print()
        console.print(f"[bold]New files[/bold] ({len(new)}):")
        for f in new:
            console.print(f"  [green]{f}[/green]")
        console.print()

    if not modified:
        console.print("[yellow]No modified files to patch (all changes are new files)[/yellow]")
        console.print("[dim]New files don't need a .patch file — commit them directly.[/dim]")
        raise typer.Exit(code=5)

    # Determine output path
    if output is None:
        patch_dir = repo / _PATCH_DIR
        patch_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(patch_dir.glob("*.patch"))
        next_num = len(existing) + 1
        branch_slug = branch.replace("feature/", "").replace("/", "-")
        output = patch_dir / f"{next_num:03d}-{branch_slug}.patch"

    if dry_run:
        console.print(f"[dim]Would write patch to: {output}[/dim]")
        console.print(f"[dim]Would include {len(modified)} modified file(s)[/dim]")
        return

    # Generate patch
    patch_content = _generate_patch(repo, merge_base, branch, modified)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patch_content)
    console.print(f"[green]Written:[/green] {output} ({len(patch_content)} bytes)")

    # Validate
    if validate:
        console.print()
        console.print("[bold]Validating patch...[/bold]")
        applies_clean, is_idempotent = _validate_patch(repo, output)

        if applies_clean:
            console.print("  [green]✅ git apply --check passed[/green]")
        else:
            console.print("  [red]❌ git apply --check failed[/red]")
            raise typer.Exit(code=3)

        if is_idempotent:
            console.print("  [green]✅ git apply --reverse --check passed (idempotent)[/green]")
        else:
            console.print("  [red]❌ git apply --reverse --check failed (not idempotent)[/red]")
            raise typer.Exit(code=4)

    # Update PATCHED_FILES
    if update_patched_files:
        console.print()
        console.print("[bold]Updating PATCHED_FILES...[/bold]")
        _update_patched_files(repo, modified)

    # Commit to base branch
    if commit:
        console.print()
        console.print(f"[bold]Committing to {base_branch}...[/bold]")

        # Switch to base branch
        _run_git(repo, "checkout", base_branch)

        # Apply the patch
        apply_result = _run_git_raw(repo, "apply", str(output), check=False)
        if apply_result.returncode != 0:
            console.print("[red]Error applying patch to base branch[/red]")
            console.print(apply_result.stderr, style="red")
            raise typer.Exit(code=3)

        # Stage patch file + new files
        _run_git(repo, "add", str(output))
        for f in new:
            # Copy new file from feature branch
            file_content = _run_git(repo, "show", f"{branch}:{f}")
            new_path = repo / f
            new_path.parent.mkdir(parents=True, exist_ok=True)
            new_path.write_text(file_content)
            _run_git(repo, "add", f)

        # Stage modified files (already applied)
        for f in modified:
            _run_git(repo, "add", f)

        # Commit
        patch_name = output.name
        commit_msg = f"feat: integrate {branch} via {patch_name}"
        _run_git(repo, "commit", "-m", commit_msg)
        console.print(f"[green]Committed:[/green] {commit_msg}")

        # Switch back
        _run_git(repo, "checkout", "-")

    console.print()
    console.print(
        Panel(
            f"[green]Done![/green]\n\n"
            f"Patch: {output}\n"
            f"Modified files: {len(modified)}\n"
            f"New files: {len(new)} (commit directly)",
            title="Summary",
        )
    )


@app.command()
def list_patches(
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        "-r",
        help="Path to the WinMux repo.",
        envvar=_REPO_ENV,
        show_default=True,
    ),
) -> None:
    """List existing .patch files in .github/patches/."""
    _list_patches(repo)


@app.command()
def analyze(
    branch: str = typer.Option(
        ...,
        "--branch",
        "-b",
        help="Feature branch to analyze.",
    ),
    base_branch: str = typer.Option(
        _DEFAULT_BASE,
        "--base",
        help="Base branch to diff against.",
        envvar=_BASE_ENV,
        show_default=True,
    ),
    repo: Path = typer.Option(
        Path.cwd(),
        "--repo",
        "-r",
        help="Path to the WinMux repo.",
        envvar=_REPO_ENV,
        show_default=True,
    ),
) -> None:
    """Show modified vs new files in a feature branch."""
    _analyze_branch(repo, base_branch, branch)


if __name__ == "__main__":
    app()
