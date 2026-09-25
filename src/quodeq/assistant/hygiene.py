"""Session and worktree cleanup: reap leaked worktrees, prune old sessions.

Pure functions taking the repository directly. The one-shot-per-process flag
and the Flask ``app`` plumbing stay in ``api._assistant_hygiene``, which
wraps ``run_hygiene`` for the route layer.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

from quodeq.assistant.worktree import gc_worktrees
from quodeq.data.ports.assistant import AssistantStore
from quodeq.shared.env_resolve import resolve_env

_logger = logging.getLogger(__name__)

# ~/.quodeq/assistant.db is never pruned otherwise; a session older than this
# is effectively dead (its worktree, if any, was reaped long before). 0
# disables. Whole-session delete cascades to its messages/events/actions.
DEFAULT_SESSION_TTL_DAYS = 90


def session_ttl_days(env: Mapping[str, str] | None = None) -> int:
    """QUODEQ_ASSISTANT_SESSION_TTL_DAYS, default 90; invalid falls back to the default."""
    raw = resolve_env(env).get("QUODEQ_ASSISTANT_SESSION_TTL_DAYS")
    if raw is None:
        return DEFAULT_SESSION_TTL_DAYS
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_SESSION_TTL_DAYS


def run_hygiene(repo: AssistantStore, ttl_days: int | None = None) -> None:
    """Reap leaked worktrees, then prune sessions older than *ttl_days*
    (default: ``session_ttl_days()``).

    Worktrees are GC'd BEFORE the session prune so a pruned session's on-disk
    worktree/branch is already gone. Never raises -- hygiene must not break
    the request that triggered it.
    """
    try:
        gc_worktrees(repo)
        removed = repo.prune_sessions_older_than(
            ttl_days if ttl_days is not None else session_ttl_days()
        )
        if removed:
            _logger.info("Pruned %d old assistant session(s)", removed)
    except Exception:  # noqa: BLE001 — hygiene is best-effort
        _logger.warning("assistant hygiene failed", exc_info=True)
