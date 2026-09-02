"""Git-worktree lifecycle for assistant fix sessions.

All git/gh invocations are argv lists (never shell strings) with explicit
-C paths. Output is decoded manually so no text-mode file handles are opened.
"""
from __future__ import annotations

import os
import subprocess
# Not called directly in this module anymore (WorktreeManager.create_pr moved
# to _worktree_manager.py) -- kept imported so this module still exposes a
# `shutil` attribute: tests patch `quodeq.assistant.worktree.shutil.which`,
# which requires that dotted path to resolve.
import shutil  # noqa: F401 - patch target attribute holder
from pathlib import Path

_GIT_TIMEOUT_S = 120

# How long an unresolved (never applied/pr'd/discarded) write worktree may
# live before GC reaps it and its quodeq/fix-* branch from the user's repo.
# Generous by default so an in-use worktree is never yanked mid-session; a
# reaped one is recreated on the next write turn. 0 disables reaping.
_DEFAULT_WORKTREE_TTL_H = 72


def _worktree_ttl_hours() -> int:
    raw = os.environ.get("QUODEQ_ASSISTANT_WORKTREE_TTL_H")
    if raw is None:
        return _DEFAULT_WORKTREE_TTL_H
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_WORKTREE_TTL_H


class WorktreeError(Exception):
    """User-facing worktree/git failure."""


def _run_bytes(argv: list[str], *, cwd: Path | None = None) -> bytes:
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


def _run(argv: list[str], *, cwd: Path | None = None) -> str:
    return _run_bytes(argv, cwd=cwd).decode("utf-8", errors="replace")


def diff_text(worktree: Path) -> str:
    """Unified diff of the worktree, including untracked files (intent-to-add).

    Diffs against HEAD, not the index: `git add -N .` records a tracked file's
    deletion in the index, so a plain worktree-vs-index diff would hide it."""
    _run(["git", "-C", str(worktree), "add", "-N", "."])
    return _run(["git", "-C", str(worktree), "diff", "HEAD"])


def diff_stats(worktree: Path) -> list[dict]:
    _run(["git", "-C", str(worktree), "add", "-N", "."])
    out = _run(["git", "-C", str(worktree), "diff", "HEAD", "--numstat"])
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
