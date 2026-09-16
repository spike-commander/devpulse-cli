"""All screen output lives here.

Commands decide WHAT to do; this module decides HOW it looks. No network
calls, no subprocess calls - feed it data, get a table. Tweak the colors to
your taste, the rest of the code won't care.
"""

from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text

CONSOLE = Console()

# state -> (style, label) for the CI column. keep labels short, they
# sit in a narrow table column
_CI_STATES: dict[str, tuple[str, str]] = {
    "success": ("green", "SUCCESS"),
    "failure": ("red", "FAILURE"),
    "error": ("red", "ERROR"),
    "pending": ("yellow", "PENDING"),
    "no_status": ("dim", "NO STATUS"),
    "unknown": ("yellow", "UNKNOWN"),
}


def loading(message: str) -> Status:
    """Spinner wrapper; use with `with loading("..."):` around slow work."""
    return CONSOLE.status(message, spinner="dots")


def error_panel(message: str) -> None:
    CONSOLE.print(
        Panel(
            Text(message, style="bold red"),
            title="devpulse error",
            border_style="red",
        )
    )


def success(message: str) -> None:
    CONSOLE.print(Text(message, style="bold green"))


# --- status ------------------------------------------------------------------


def render_pr_table(pull_requests: list[dict[str, Any]]) -> None:
    """Open PRs with title, repo, branch, age, and CI signal."""
    if not pull_requests:
        success("No open pull requests. nice and tidy.")
        return

    table = Table(title="Open Pull Requests", box=box.ROUNDED)
    table.add_column("Title", style="bold")
    table.add_column("Repository", style="cyan")
    table.add_column("Branch", style="magenta")
    table.add_column("Created", style="dim")
    table.add_column("CI", justify="center")

    for pr in pull_requests:
        table.add_row(
            pr["title"],
            pr["repository"],
            pr["branch"],
            _format_date(pr.get("created_at")),
            _ci_status_text(pr.get("ci_status", "no_status")),
        )
    CONSOLE.print(table)


def _ci_status_text(state: str) -> Text:
    style, label = _CI_STATES.get(state, ("dim", state.upper()))
    return Text(label, style=f"bold {style}")


def _format_date(iso_value: str | None) -> str:
    if not iso_value:
        return "-"
    try:
        # github timestamps end in 'Z'; fromisoformat handles that since 3.11
        parsed = datetime.fromisoformat(iso_value)
    except ValueError:
        return iso_value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


# --- prune -------------------------------------------------------------------


def render_prune_table(branches: list[str], base: str) -> None:
    """Merged branches, numbered so the eye can scan them."""
    if not branches:
        success(f"Nothing merged into '{base}'. your tree is clean.")
        return

    table = Table(title=f"Branches merged into '{base}'", box=box.SIMPLE)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Branch", style="bold")
    for i, branch in enumerate(branches, start=1):
        table.add_row(str(i), Text(branch, style="cyan"))
    CONSOLE.print(table)
    CONSOLE.print("dry run. add --delete to actually remove them.", style="dim")


def render_deleted_branches(deleted: list[str]) -> None:
    if not deleted:
        return
    table = Table(title="Deleted branches", box=box.SIMPLE)
    table.add_column("Branch", style="bold red")
    for branch in deleted:
        table.add_row(branch)
    CONSOLE.print(table)


# --- scan --------------------------------------------------------------------


def render_index_table(entries: list[dict[str, Any]]) -> None:
    """Inventory of a knowledge base: lines, words, headings per file."""
    if not entries:
        success("No markdown files found to index.")
        return

    total_lines = sum(e["line_count"] for e in entries)
    total_words = sum(e["word_count"] for e in entries)

    table = Table(title="Markdown Knowledge Base Index", box=box.ROUNDED)
    table.add_column("File", style="bold")
    table.add_column("Lines", justify="right", style="dim")
    table.add_column("Words", justify="right", style="dim")
    table.add_column("Headings", justify="right", style="dim")
    table.add_column("Sample headings", style="magenta")

    for entry in entries:
        table.add_row(
            entry["path"],
            str(entry["line_count"]),
            str(entry["word_count"]),
            str(entry["heading_count"]),
            entry["sample_headings"],
        )

    CONSOLE.print(table)
    CONSOLE.print(
        f"{len(entries)} file(s), {total_lines} lines, {total_words} words.",
        style="dim",
    )