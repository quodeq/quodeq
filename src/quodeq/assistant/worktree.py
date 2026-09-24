"""Git-worktree lifecycle for assistant fix sessions.

All git/gh invocations are argv lists (never shell strings) with explicit
-C paths. Output is decoded manually so no text-mode file handles are opened.
"""
from __future__ import annotations

import subprocess
# Not called directly in this module anymore (WorktreeManager.create_pr moved
# to _worktree_manager.py) -- kept imported so this module still exposes a
# `shutil` attribute: tests patch `quodeq.assistant.worktree.shutil.which`,
# which requires that dotted path to resolve.
import shutil  # noqa: F401 - patch target attribute holder
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from quodeq.assistant._constants import ENCODING_UTF8
from quodeq.shared.env_resolve import resolve_env

GIT_BIN = "git"  # argv[0] for every git invocation in this module and _worktree_manager.py
GIT_FLAG_C = "-C"  # -C <path>: run git against that repo without cd'ing there


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
    if argv[0] == GIT_BIN:
        # never let core.autocrlf (Git-for-Windows default: true) rewrite line
        # endings at checkout/diff/apply; the tool contract is byte-exact files
        argv = [GIT_BIN, "-c", "core.autocrlf=false", *argv[1:]]
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv, cwd=str(cwd) if cwd else None,
            capture_output=True, timeout=_GIT_TIMEOUT_S, check=False)
    except FileNotFoundError as exc:
        raise WorktreeError(f"{argv[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError(f"{argv[0]} timed out") from exc
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode(ENCODING_UTF8, errors="replace")
        out = (proc.stdout or b"").decode(ENCODING_UTF8, errors="replace")
        raise WorktreeError((err or out).strip() or f"{argv[0]} failed")
    return proc.stdout or b""


def run_git(argv: list[str], *, cwd: Path | None = None) -> str:
    """Run *argv* and return its stdout decoded as UTF-8."""
    return run_git_bytes(argv, cwd=cwd).decode(ENCODING_UTF8, errors="replace")


def diff_text(worktree: Path) -> str:
    """Unified diff of the worktree, including untracked files (intent-to-add).

    Diffs against HEAD, not the index: `git add -N .` records a tracked file's
    deletion in the index, so a plain worktree-vs-index diff would hide it."""
    run_git([GIT_BIN, GIT_FLAG_C, str(worktree), "add", "-N", "."])
    return run_git([GIT_BIN, GIT_FLAG_C, str(worktree), "diff", "HEAD"])


def diff_stats(worktree: Path) -> list[dict]:
    """Per-file added/deleted counts for the worktree's pending changes.

    Binary files report 0/0 (numstat writes "-"). Unparseable lines are
    skipped rather than raising.
    """
    run_git([GIT_BIN, GIT_FLAG_C, str(worktree), "add", "-N", "."])
    out = run_git([GIT_BIN, GIT_FLAG_C, str(worktree), "diff", "HEAD", "--numstat"])
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


# Re-exported: moved to _worktree_manager.py / _worktree_gc.py to keep this
# module under 300 lines. Both modules import their git/error primitives back
# from here, so this module must load first (no cycle: the imports below run
# after this module's own definitions above are already in place).
from quodeq.assistant._worktree_manager import (  # noqa: F401, E402
    WorktreeManager, ensure_session_worktree,
)
from quodeq.assistant._worktree_gc import (  # noqa: F401, E402
    gc_stale_worktrees, gc_worktrees,
)
