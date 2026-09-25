"""One-shot-per-process gate for assistant cleanup, and the shared-source-gone
error type build_tool_context raises.

Split out of _assistant_helpers.py. ``get_repository`` is imported directly
from ``_assistant_location`` (its real owner), not looked up on the
``_assistant_helpers`` facade, so this module never imports back the facade
that re-exports it. The cleanup logic itself (worktree GC + session prune)
lives in ``quodeq.assistant.hygiene``, re-exported here so this stays the
one place both are patched from.
"""
from __future__ import annotations

from flask import Flask

from quodeq.api._assistant_location import get_repository
from quodeq.assistant.hygiene import (  # noqa: F401 — re-export/patch target
    DEFAULT_SESSION_TTL_DAYS as _DEFAULT_SESSION_TTL_DAYS,
    run_hygiene,
    session_ttl_days,
)


class SharedSourceUnavailable(RuntimeError):
    """A shared-source session's clone is gone (repo disconnected)."""


def run_assistant_hygiene(app: Flask, *, ttl_days: int | None = None) -> None:
    """Run assistant hygiene once per process, on the first assistant request.

    The one-shot flag is set before running, so a hygiene failure still
    won't re-run (or break) the next request either.
    """
    if getattr(app, "_assistant_hygiene_done", False):
        return
    app._assistant_hygiene_done = True
    run_hygiene(get_repository(app), ttl_days)
