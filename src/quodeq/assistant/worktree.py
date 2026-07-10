"""Git-worktree lifecycle for assistant fix sessions.

All git/gh invocations are argv lists (never shell strings) with explicit
-C paths. Output is decoded manually so no text-mode file handles are opened.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_GIT_TIMEOUT_S = 120
_BRANCH_PREFIX = "quodeq/fix-"
_MAX_BRANCH_TRIES = 5


class WorktreeError(Exception):
    """User-facing worktree/git failure."""


def _run(argv: list[str], *, cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv, cwd=str(cwd) if cwd else None,
            capture_output=True, timeout=_GIT_TIMEOUT_S, check=False)
    except FileNotFoundError as exc:
        raise WorktreeError(f"{argv[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError(f"{argv[0]} timed out") from exc
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise WorktreeError((err or out).strip() or f"{argv[0]} failed")
    return out


def diff_text(worktree: Path) -> str:
    """Unified diff of the worktree, including untracked files (intent-to-add)."""
    _run(["git", "-C", str(worktree), "add", "-N", "."])
    return _run(["git", "-C", str(worktree), "diff"])


def diff_stats(worktree: Path) -> list[dict]:
    _run(["git", "-C", str(worktree), "add", "-N", "."])
    out = _run(["git", "-C", str(worktree), "diff", "--numstat"])
    stats = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            added, deleted, name = parts
            stats.append({"file": name,
                          "added": 0 if added == "-" else int(added),
                          "deleted": 0 if deleted == "-" else int(deleted)})
    return stats


def worktrees_base() -> Path:
    return Path(os.environ.get(
        "QUODEQ_WORKTREES_DIR", str(Path.home() / ".quodeq" / "worktrees")))


@dataclass
class WorktreeManager:
    repo_root: Path
    path: Path
    branch: str

    @classmethod
    def for_session(cls, repo_root: Path, project_id: str, session_id: str,
                    base: Path | None = None) -> "WorktreeManager":
        base = base or worktrees_base()
        short = session_id[:8]
        return cls(repo_root=Path(repo_root),
                   path=base / (project_id or "project") / short,
                   branch=f"{_BRANCH_PREFIX}{short}")

    def exists(self) -> bool:
        return self.path.is_dir() and (self.path / ".git").exists()

    def create(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "-C", str(self.repo_root), "worktree", "prune"])
        last_err: WorktreeError | None = None
        for attempt in range(_MAX_BRANCH_TRIES):
            candidate = (self.branch if attempt == 0
                         else f"{self.branch}-{attempt + 1}")
            try:
                _run(["git", "-C", str(self.repo_root), "worktree", "add",
                      "-b", candidate, str(self.path)])
                self.branch = candidate
                return
            except WorktreeError as exc:
                last_err = exc
                if "already exists" not in str(exc):
                    raise
        raise WorktreeError(f"could not allocate a fix branch: {last_err}")

    def diff(self) -> str:
        return diff_text(self.path)

    def remove(self, delete_branch: bool = True) -> None:
        if self.exists():
            _run(["git", "-C", str(self.repo_root), "worktree", "remove",
                  "--force", str(self.path)])
        else:
            shutil.rmtree(self.path, ignore_errors=True)
            _run(["git", "-C", str(self.repo_root), "worktree", "prune"])
        if delete_branch:
            try:
                _run(["git", "-C", str(self.repo_root), "branch", "-D", self.branch])
            except WorktreeError:
                pass  # branch already gone; removal is best-effort
