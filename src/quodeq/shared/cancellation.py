"""Process-wide cancellation signal for long-running evaluations.

One evaluation runs per Python process. The SIGTERM/SIGINT handler in
run_lifecycle calls ``request_cancel()``; worker threads deep in the
analysis pipeline poll ``is_cancelled()`` (or wait on ``get_event()``) so
they can terminate their child AI CLI subprocesses promptly instead of
blocking ``ThreadPoolExecutor.shutdown`` on long Ollama inference calls.
"""
from __future__ import annotations

import threading

_event = threading.Event()
_reason: str | None = None


def get_event() -> threading.Event:
    return _event


def is_cancelled() -> bool:
    return _event.is_set()


def request_cancel(reason: str | None = None) -> None:
    """Set the cancellation flag, optionally recording why.

    Only the first non-None *reason* wins: later callers (e.g. the signal
    handler firing after a provider-fatal cancel) must not overwrite the
    original cause that ``cancel_reason()`` reports.
    """
    global _reason
    if reason is not None and _reason is None:
        _reason = reason
    _event.set()


def cancel_reason() -> str | None:
    """Why the run was cancelled, when the canceller recorded a reason."""
    return _reason


def reset() -> None:
    global _reason
    _reason = None
    _event.clear()
