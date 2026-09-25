"""Low-level git primitives and constants for the assistant worktree layer.

Split out of ``worktree.py`` to break its facade cycle with
``_worktree_manager.py`` / ``_worktree_gc.py``: those two modules used to
import these primitives back from ``worktree.py`` (which itself imports
them at the bottom, after re-exporting ``WorktreeManager`` etc.), relying on
Python's partial-module-init ordering to avoid a real ImportError. This
module is a true leaf -- it imports nothing from ``worktree.py``,
``_worktree_manager.py``, or ``_worktree_gc.py`` -- so every consumer,
including ``worktree.py`` itself, imports it as a plain top-level import.

All git/gh invocations are argv lists (never shell strings) with explicit
-C paths. Output is decoded manually so no text-mode file handles are opened.
"""
from __future__ import annotations

import subprocess
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from quodeq.shared.env_resolve import resolve_env


class WorktreeStatus(StrEnum):
    """A session's fix-worktree row lifecycle.

    data/sqlite/_assistant_schema.py's ``worktrees.status`` CHECK mirrors
    these values (SQL text can't reference this name, so the two are kept
    equal by tests/data/sqlite/test_assistant_schema.py instead). Distinct
    from workspace_actions.OutcomeKind even where a word ("applied") coincides.
    """

    ACTIVE = "active"
    APPLIED = "applied"
    PR_CREATED = "pr_created"
    DISCARDED = "discarded"
    STALE = "stale"


_GIT_TIMEOUT_S = 120

# How long an unresolved (never applied/pr'd/discarded) write worktree may
# live before GC reaps it and its quodeq/fix-* branch from the user's repo.
# Generous by default so an in-use worktree is never yanked mid-session; a
# reaped one is recreated on the next write turn. 0 disables reaping.
_DEFAULT_WORKTREE_TTL_H = 72


def worktree_ttl_hours(env: Mapping[str, str] | None = None) -> int:
    """Hours an unresolved write worktree may live before GC; 0 disables reaping."""
    raw = resolve_env(env).get("QUODEQ_ASSISTANT_WORKTREE_TTL_H")
    if raw is None:
        return _DEFAULT_WORKTREE_TTL_H
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_WORKTREE_TTL_H


class WorktreeError(Exception):
    """User-facing worktree/git failure."""


def run_git_bytes(argv: list[str], *, cwd: Path | None = None) -> bytes:
    """Run *argv* and return its stdout bytes, raising WorktreeError on failure."""
    if argv[0] == "git":
        # never let core.autocrlf (Git-for-Windows default: true) rewrite line
        # endings at checkout/diff/apply; the tool contract is byte-exact files
        argv = ["git", "-c", "core.autocrlf=false", *argv[1:]]
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv, cwd=str(cwd) if cwd else None,
            capture_output=True, timeout=_GIT_TIMEOUT_S, check=False)
    except FileNotFoundError as exc:
        raise WorktreeError(f"{argv[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError(f"{argv[0]} timed out") from exc
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        raise WorktreeError((err or out).strip() or f"{argv[0]} failed")
    return proc.stdout or b""


def run_git(argv: list[str], *, cwd: Path | None = None) -> str:
    """Run *argv* and return its stdout decoded as UTF-8."""
    return run_git_bytes(argv, cwd=cwd).decode("utf-8", errors="replace")


def diff_text(worktree: Path) -> str:
    """Unified diff of the worktree, including untracked files (intent-to-add).

    Diffs against HEAD, not the index: `git add -N .` records a tracked file's
    deletion in the index, so a plain worktree-vs-index diff would hide it."""
    run_git(["git", "-C", str(worktree), "add", "-N", "."])
    return run_git(["git", "-C", str(worktree), "diff", "HEAD"])


def diff_stats(worktree: Path) -> list[dict]:
    """Per-file added/deleted counts for the worktree's pending changes.

    Binary files report 0/0 (numstat writes "-"). Unparseable lines are
    skipped rather than raising.
    """
    run_git(["git", "-C", str(worktree), "add", "-N", "."])
    out = run_git(["git", "-C", str(worktree), "diff", "HEAD", "--numstat"])
    stats = []
    for line in out.splitlines():
        try:
            added, deleted, name = line.split("\t")
        except ValueError:
            continue
        stats.append({"file": name,
                      "added": 0 if added == "-" else int(added),
                      "deleted": 0 if deleted == "-" else int(deleted)})
    return stats


def worktrees_base(env: Mapping[str, str] | None = None) -> Path:
    """Directory that holds every assistant worktree, overridable with
    ``QUODEQ_WORKTREES_DIR``. Not created here."""
    raw = resolve_env(env).get("QUODEQ_WORKTREES_DIR")
    return Path(raw) if raw else Path.home() / ".quodeq" / "worktrees"
