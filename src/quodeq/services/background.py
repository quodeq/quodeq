"""Fire-and-forget background task submission.

Extracted so a route handler (``api/_evaluation_routes.py``'s salvage-scoring
GET) and a service-layer mutation flow (``services/mutation_rescore.py``'s
project-wide projection fallback) share one seam for "run this off the
current thread" instead of each spawning its own ``threading.Thread``.
Distinct from ``EvaluationDispatcher`` (``services/evaluation_mixin.py``),
which dispatches a whole evaluation subprocess; this is for small, in-process
work items that must not block the caller.
"""
from __future__ import annotations

import threading
from typing import Callable, Protocol

from quodeq.core.observability import NULL_LOG, LogSink


class BackgroundRunner(Protocol):
    """Abstraction for running a callable off the current thread."""

    def submit(self, fn: Callable[[], None], *, name: str = "") -> None:
        """Schedule *fn* to run in the background. Must never block/join."""
        ...


class ThreadBackgroundRunner:
    """Default runner: one daemon thread per submission.

    Exceptions raised by *fn* are swallowed and logged at debug level — by
    the time the work runs, the caller has already returned its response (or,
    for the service-layer caller, already returned its own result), so there
    is no request left to report the failure to.
    """

    def __init__(self, *, log: LogSink = NULL_LOG) -> None:
        self._log = log

    def submit(self, fn: Callable[[], None], *, name: str = "") -> None:
        def _run() -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — background work must never crash the thread silently
                self._log.debug(f"Background task {name or fn} failed: {exc}")

        threading.Thread(target=_run, name=name or None, daemon=True).start()
