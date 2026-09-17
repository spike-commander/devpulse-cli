"""devpulse command layer.

Deliberately thin: parse args, call a service, hand results to the
visualizer. If a command grows past ~20 lines here, that logic belongs in a
module of its own.
"""

import asyncio
import re
from pathlib import Path
from typing import Annotated, Any

import typer

from devpulse.core.git_client import GitClient, GitException
from devpulse.services.github_svc import GitHubService, GitHubServiceError
from devpulse.utils.visualizer import (
    error_panel,
    loading,
    render_deleted_branches,
    render_index_table,
    render_pr_table,
    render_prune_table,
    success,
)

app = typer.Typer(
    name="devpulse",
    help="git hygiene, pr status, note indexing. pick one.",
    no_args_is_help=True,
)

# "# Heading" -> "Heading"; group 1 is the text without the #'s
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


@app.command(help="Fetch live PR metrics for the authenticated GitHub user.")
def status(
    token: Annotated[
        str,
        typer.Option(
            envvar="GITHUB_TOKEN",
            help="GitHub personal access token (or set GITHUB_TOKEN).",
        ),
    ],
) -> None:
    """Asks the GitHub API about the current user's open PRs."""
    try:
        service = GitHubService()
        with loading("querying github for your open PRs ..."):
            pull_requests = asyncio.run(service.fetch_user_pull_requests(token))
    except GitHubServiceError as exc:
        error_panel(str(exc))
        raise typer.Exit(code=1) from exc
    render_pr_table(pull_requests)


@app.command(help="List (and optionally delete) branches already merged into a base.")
def prune(
    base: Annotated[
        str,
        typer.Option(help="Base branch to compare merged work against."),
    ] = "main",
    delete: Annotated[
        bool,
        typer.Option("--delete", help="Delete merged branches instead of listing."),
    ] = False,
) -> None:
    """Local hygiene: find branches that are just dead weight."""
    try:
        git = GitClient.create()
        with loading("syncing remote-tracking branches ..."):
            git.update_remotes()
        branches = git.merged_branches(base)
    except GitException as exc:
        error_panel(str(exc))
        raise typer.Exit(code=1) from exc

    if not delete:
        render_prune_table(branches, base)
        return

    deleted: list[str] = []
    failed: list[str] = []
    for branch in branches:
        try:
            git.delete_branch(branch)
            deleted.append(branch)
        except GitException:
            # git -d refused: the branch sits on commits base doesn't have
            failed.append(branch)

    render_deleted_branches(deleted)
    if not deleted:
        success(f"No merged branches to delete against '{base}'.")
    if failed:
        error_panel(
            "couldn't remove: "
            + ", ".join(failed)
            + " -- they carry commits '"
            + base
            + "' doesn't have. delete them manually if you're sure."
        )


@app.command(help="Index a local Markdown knowledge base into an inventory report.")
def scan(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Markdown file or directory. Defaults to cwd."),
    ] = None,
) -> None:
    """Walk a notes folder and report what's actually in it."""
    target = path if path is not None else Path.cwd()
    if not target.exists():
        error_panel(f"no such path: {target}")
        raise typer.Exit(code=1)

    with loading(f"indexing markdown under {target.resolve()} ..."):
        entries = _index_notes(target)
    render_index_table(entries)


# --- internal helpers ---------------------------------------------------------


def _index_notes(target: Path) -> list[dict[str, Any]]:
    """Collect line/word/heading counts for every markdown file found."""
    files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    entries: list[dict[str, Any]] = []
    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""  # binary file with a .md extension; skip quietly
        headings = _extract_headings(file)
        entries.append(
            {
                "path": str(file),
                "line_count": text.count("\n") + (1 if text else 0),
                "word_count": len(text.split()),
                "heading_count": len(headings),
                "sample_headings": ", ".join(headings[:3]),
            }
        )
    return entries


def _extract_headings(file: Path) -> list[str]:
    """Just the heading text, no leading #'s."""
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return [m.group(1).strip() for line in lines if (m := _HEADING.match(line.strip()))]