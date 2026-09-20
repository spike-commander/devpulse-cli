from pathlib import Path

from typer.testing import CliRunner

from devpulse.cli import app
from devpulse.core.git_client import GitClient, GitException

runner = CliRunner()


def test_cli_help_shows_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("status", "prune", "scan"):
        assert command in result.output


def test_git_client_fails_outside_repo(tmp_path: Path) -> None:
    try:
        GitClient.create(cwd=tmp_path)
    except GitException as exc:
        assert "not a git repo" in str(exc)
    else:
        raise AssertionError("expected GitException outside a git repo")


def test_scan_indexes_markdown(tmp_path: Path) -> None:
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "ideas.md").write_text("# Work\n\n- one\n- two\n", encoding="utf-8")
    (notes / "todo.md").write_text("no headings here\n", encoding="utf-8")

    result = runner.invoke(app, ["scan", "--path", str(notes)])

    assert result.exit_code == 0
    assert "2 file" in result.output
    assert "Work" in result.output


def test_heading_regex_matches_atx_headings() -> None:
    from devpulse.cli import _HEADING

    assert _HEADING.match("# Title").group(1) == "Title"
    assert _HEADING.match("### Deep").group(1) == "Deep"
    assert _HEADING.match("not a heading") is None