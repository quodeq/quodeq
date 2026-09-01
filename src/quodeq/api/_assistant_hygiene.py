"""One-shot-per-process assistant cleanup: reap leaked worktrees, prune old
sessions; and the shared-source-gone error type build_tool_context raises.

Split out of _assistant_helpers.py (Task 10).
"""
from __future__ import annotations

import logging
import os

from flask import Flask

_logger = logging.getLogger(__name__)


class SharedSourceUnavailable(RuntimeError):
    """A shared-source session's clone is gone (repo disconnected)."""

# ~/.quodeq/assistant.db is never pruned otherwise; a session older than this
# is effectively dead (its worktree, if any, was reaped long before). 0
# disables. Whole-session delete cascades to its messages/events/actions.
_DEFAULT_SESSION_TTL_DAYS = 90


def _session_ttl_days() -> int:
    raw = os.environ.get("QUODEQ_ASSISTANT_SESSION_TTL_DAYS")
    if raw is None:
        return _DEFAULT_SESSION_TTL_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_SESSION_TTL_DAYS


def run_assistant_hygiene(app: Flask) -> None:
    """One-shot-per-process cleanup: reap leaked worktrees, prune old sessions.

    Runs on the first assistant request. Worktrees are GC'd BEFORE the session
    prune so a pruned session's on-disk worktree/branch is already gone.
    Never raises — hygiene must not break the request that triggered it.
    """
    if getattr(app, "_assistant_hygiene_done", False):
        return
    app._assistant_hygiene_done = True
    from quodeq.assistant.worktree import gc_worktrees  # noqa: PLC0415
    # Deferred: _assistant_helpers re-exports this module's names, so a
    # module-level import here would cycle back into a partially-initialized
    # _assistant_helpers.
    from quodeq.api import _assistant_helpers as _helpers  # noqa: PLC0415
    repo = _helpers.get_repository(app)
    try:
        gc_worktrees(repo)
        removed = repo.prune_sessions_older_than(_session_ttl_days())
        if removed:
            _logger.info("Pruned %d old assistant session(s)", removed)
    except Exception:  # noqa: BLE001 — hygiene is best-effort
        _logger.warning("assistant hygiene failed", exc_info=True)
