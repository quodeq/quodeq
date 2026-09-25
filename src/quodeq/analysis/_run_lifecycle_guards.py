"""Signal and atexit guards for RunLifecycleContext.

Split out of ``_run_lifecycle_support.py`` (file-size ratchet): installing/
restoring the run's OS signal handlers and registering/deregistering the
atexit fallback hook are self-contained process-level primitives with no
dependency on the lifecycle state machine. Re-exported from
``_run_lifecycle_support`` so existing imports (including grandfathered
test imports) keep resolving there.
"""
from __future__ import annotations

import atexit
import signal
from collections.abc import Callable
from typing import Any

from quodeq.core.observability import NULL_LOG, LogSink

# Public name: re-imported (aliased back to the historical private spelling)
# from _run_lifecycle_support.py, which the private-import gate would
# otherwise flag as a cross-file `_name` import (rule 2).
SIGNALS_TO_HANDLE = (signal.SIGINT, signal.SIGTERM)
# SIGHUP is POSIX-only. Included conditionally below.
if hasattr(signal, "SIGHUP"):
    SIGNALS_TO_HANDLE = SIGNALS_TO_HANDLE + (signal.SIGHUP,)

# A signal handler's shape: (signum, frame) -> None.
SignalHandler = Callable[[int, Any], None]


class SignalGuard:
    """Install *handler* on the run's signals; restore the originals after."""

    def __init__(self, handler: SignalHandler, *, log: LogSink = NULL_LOG) -> None:
        self._handler = handler
        self._previous: dict[int, Any] = {}
        self._log = log

    def install(self) -> None:
        for sig in SIGNALS_TO_HANDLE:
            try:
                self._previous[sig] = signal.getsignal(sig)
                signal.signal(sig, self._handler)
            except (OSError, ValueError) as exc:
                # Can fail in non-main threads; tests may run under such a case.
                self._log.debug(f"signal handler for {sig!r} not installed: {exc}")

    def restore(self) -> None:
        for sig, prev in self._previous.items():
            try:
                signal.signal(sig, prev)
            except (OSError, ValueError) as exc:
                self._log.debug(f"signal handler for {sig!r} not restored: {exc}")
        self._previous.clear()


class AtexitGuard:
    """Register *callback* with atexit once, and deregister it once."""

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._registered = False

    def register(self) -> None:
        atexit.register(self._callback)
        self._registered = True

    def deregister(self) -> None:
        if not self._registered:
            return
        # atexit.unregister is a no-op for a callback that is not registered
        # and does not raise for one; there is nothing to guard.
        atexit.unregister(self._callback)
        self._registered = False
