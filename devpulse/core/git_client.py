"""Puppeteering git itself.

Every function here shells out to the real git binary. We always use
capture_output=True so nothing leaks to the terminal, and failures come back
as a single GitException type instead of a grab-bag of subprocess errors.
"""

import subprocess
from pathlib import Path


class GitException(Exception):
    """anything git-related that went wrong, wrapped neatly."""


class GitClient:
    def __init__(self, root: Path):
        self._root = root

    @classmethod
    def create(cls, cwd: Path | None = None) -> "GitClient":
        """Point us at the repo containing cwd (default: wherever the user is)."""
        start = cwd if cwd is not None else Path.cwd()
        return cls(cls._find_root(start))

    @staticmethod
    def _find_root(start: Path) -> Path:
        try:
            # check=False on purpose: we read returncode ourselves below
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(start),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise GitException(
                "couldn't run git - is it installed and on PATH?"
            ) from exc

        if result.returncode != 0:
            detail = result.stderr.strip()
            raise GitException(
                f"'{start}' is not a git repo" + (f" ({detail})" if detail else "")
            )

        top = result.stdout.strip()
        if not top:
            raise GitException("git rev-parse came back empty, go figure")
        return Path(top)

    @property
    def root(self) -> Path:
        return self._root

    def run(self, *args: str) -> str:
        """`git <args>`; returns trimmed stdout or raises GitException."""
        cmd = ("git", *args)
        try:
            result = subprocess.run(
                cmd, cwd=str(self._root), capture_output=True, text=True, check=False
            )
        except OSError as exc:
            raise GitException(
                "couldn't run git - is it installed and on PATH?"
            ) from exc

        if result.returncode != 0:
            msg = result.stderr.strip() or result.stdout.strip()
            raise GitException(msg or f"'git {' '.join(args)}' failed, silent")
        return result.stdout.strip()

    def update_remotes(self) -> None:
        # --prune so remote branches that were deleted stop shadowing reality
        self.run("remote", "update", "--prune")

    def current_branch(self) -> str | None:
        branch = self.run("rev-parse", "--abbrev-ref", "HEAD")
        return branch if branch not in ("", "HEAD") else None

    def merged_branches(self, base: str) -> list[str]:
        """Local branches fully merged into `base` (excluding the one checked out)."""
        raw = self.run("branch", "--merged", base, "--format=%(refname:short)")
        current = self.current_branch()
        branches = []
        for name in raw.splitlines():
            name = name.strip()
            if name and name != base and name != current:
                branches.append(name)
        return branches

    def delete_branch(self, branch: str) -> None:
        # -d, not -D: git refuses when there are unpushed/unmerged commits
        self.run("branch", "-d", branch)