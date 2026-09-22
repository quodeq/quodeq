"""Reap leaked assistant worktrees and their ``quodeq/fix-*`` branches.

Split from ``worktree.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from quodeq.assistant._worktree_manager import WorktreeManager
from quodeq.assistant.worktree import WorktreeError, _worktree_ttl_hours

_logger = logging.getLogger(__name__)


def _row_age_hours(created_at: str | None, now: datetime) -> float | None:
    """Hours since *created_at* (a SQLite datetime string), or None if unparsable."""
    if not created_at:
        return None
    text = str(created_at).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return (now - dt).total_seconds() / 3600.0
        except ValueError:
            continue
    return None


def _remove_worktree_row(row: dict) -> None:
    """Best-effort remove of a worktree dir + its branch from the row data."""
    try:
        WorktreeManager(
            repo_root=Path(row["repo_root"]), path=Path(row["path"]),
            branch=row["branch"],
        ).remove()
    except WorktreeError as exc:
        _logger.warning("GC could not remove worktree %s: %s", row["path"], exc)


def gc_worktrees(repository, ttl_hours: int | None = None) -> None:
    """Reap leaked assistant worktrees + their ``quodeq/fix-*`` branches.

    Cleanup only happened on explicit apply/pr/discard, so a write session the
    user never resolved (a new session is minted per context switch / "New
    conversation") left its worktree and branch in the real repo forever, and
    a failed ``remove`` left a terminal row whose worktree the old GC never
    revisited. This reaps three cases:

      * ``active`` row, dir vanished  -> mark ``stale`` (crash cleanup).
      * ``active`` row older than the TTL, dir exists -> abandoned: remove
        the worktree + branch, mark ``discarded``.
      * terminal row (applied/pr_created/discarded/stale), dir still exists
        -> a prior ``remove`` failed: retry the removal.

    ``ttl_hours=0`` treats every active worktree as reapable (used by tests);
    a young active worktree is otherwise left untouched so an in-use session
    is never yanked mid-edit.
    """
    ttl = _worktree_ttl_hours() if ttl_hours is None else ttl_hours
    now = datetime.now(timezone.utc)
    try:
        rows = repository.list_all_worktrees()
    except AttributeError:  # older repository without the new method
        rows = repository.list_worktrees("active")
    for row in rows:
        dir_exists = Path(row["path"]).is_dir()
        if row["status"] == "active":
            if not dir_exists:
                repository.set_worktree_status(row["session_id"], "stale")
                continue
            age = _row_age_hours(row["created_at"], now)
            if ttl <= 0 or (age is not None and age >= ttl):
                _remove_worktree_row(row)
                repository.set_worktree_status(row["session_id"], "discarded")
        elif dir_exists:
            # Terminal row whose worktree a failed remove left behind: retry.
            _remove_worktree_row(row)


# Back-compat alias: the workspace route's one-shot GC calls this name.
def gc_stale_worktrees(repository) -> None:
    """Deprecated name for :func:`gc_worktrees` (kept for existing callers)."""
    gc_worktrees(repository)
