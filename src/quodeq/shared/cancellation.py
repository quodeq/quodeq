"""Process-wide cancellation signal for long-running evaluations.

One evaluation runs per Python process. The SIGTERM/SIGINT handler in
run_lifecycle calls ``request_cancel()``; worker threads deep in the
analysis pipeline poll ``is_cancelled()`` (or wait on ``get_event()``) so
they can terminate their child AI CLI subprocesses promptly instead of
blocking ``ThreadPoolExecutor.shutdown`` on long Ollama inference calls.
"""
from __future__ import annotations

import threading


class CancellationToken:
    """A single cancellation flag: a threading.Event plus an optional reason.

    ``_DEFAULT`` below is the process-wide instance the module-level
    functions delegate to. The signal handler binding is the reason a
    default instance still exists here: SIGTERM/SIGINT handlers cannot
    receive an injected token, so the composition seam is the module facade
    itself, same shape as the accepted ``SHARED_LOG`` default.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    def get_event(self) -> threading.Event:
        return self._event

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def request_cancel(self, reason: str | None = None) -> None:
        """Set the cancellation flag, optionally recording why.

        Only the first non-None *reason* wins: later callers (e.g. the signal
        handler firing after a provider-fatal cancel) must not overwrite the
        original cause that ``cancel_reason()`` reports.
        """
        if reason is not None and self._reason is None:
            self._reason = reason
        self._event.set()

    def cancel_reason(self) -> str | None:
        """Why the run was cancelled, when the canceller recorded a reason."""
        return self._reason

    def reset(self) -> None:
        self._reason = None
        self._event.clear()


_DEFAULT = CancellationToken()


def get_event() -> threading.Event:
    return _DEFAULT.get_event()


def is_cancelled() -> bool:
    return _DEFAULT.is_cancelled()


def request_cancel(reason: str | None = None) -> None:
    _DEFAULT.request_cancel(reason)


def cancel_reason() -> str | None:
    return _DEFAULT.cancel_reason()


def reset() -> None:
    _DEFAULT.reset()
