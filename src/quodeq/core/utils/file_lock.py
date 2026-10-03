"""Platform-specific file locking helpers.

Provides ``lock_file`` and ``unlock_file`` that dispatch to the correct
OS primitive (``fcntl`` on Unix, ``msvcrt`` on Windows).

Lives in core (stdlib-only, no outward imports) so any layer can use it
without reaching into ``data/``. ``data/file_lock.py`` re-exports it for
the rest of the codebase.
"""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable

from quodeq.core.constants import PLATFORM_WIN32

_logger = logging.getLogger(__name__)

# Lock budget for both platforms. Windows' blocking msvcrt.LK_LOCK only
# retries 10x at 1s, which is too short under the subagent pool's heavy
# contention, and Unix flock has no built-in timeout, so both poll the
# non-blocking primitive in _poll_lock with this budget and cadence.
_LOCK_TIMEOUT_S = 60.0
_LOCK_RETRY_INTERVAL_S = 0.05


def _budget(timeout_s: float | None) -> float:
    """*timeout_s*, or ``_LOCK_TIMEOUT_S`` when it is None.

    Read at call time rather than as a default arg: tests monkeypatch the
    module constant to keep the contention case fast.
    """
    return _LOCK_TIMEOUT_S if timeout_s is None else timeout_s


def _poll_lock(try_lock: Callable[[], None], budget: float) -> None:
    """Call *try_lock* until it stops raising OSError; after *budget* seconds the last one propagates."""
    deadline = time.monotonic() + budget
    while True:
        try:
            try_lock()
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_LOCK_RETRY_INTERVAL_S)


def _make_lock_ops() -> tuple:
    """Return (lock_fn, unlock_fn) for the current platform."""
    if sys.platform == PLATFORM_WIN32:
        import msvcrt

        def _lock(fd: int, timeout_s: float | None = None) -> None:
            _poll_lock(lambda: msvcrt.locking(fd, msvcrt.LK_NBLCK, 1), _budget(timeout_s))

        def _unlock(fd: int) -> None:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        def _lock(fd: int, timeout_s: float | None = None) -> None:
            budget = _budget(timeout_s)
            _logger.debug(
                "Waiting for file lock (timeout %.0fs)", budget,
            )
            try:
                _poll_lock(lambda: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB), budget)
            except OSError:
                _logger.warning(
                    "Timed out after %.0fs waiting for file lock", budget,
                )
                raise TimeoutError(
                    f"Timed out waiting for file lock after {budget}s",
                ) from None

        def _unlock(fd: int) -> None:
            fcntl.flock(fd, fcntl.LOCK_UN)
    return _lock, _unlock


_lock_impl, _unlock_impl = _make_lock_ops()


def lock_file(fd: int, timeout_s: float | None = None) -> None:
    """Acquire an exclusive lock on the file descriptor.

    *timeout_s* overrides the default 60s budget, which is sized for the
    subagent pool's heavy contention and is far too long to hold an HTTP
    request thread. Callers on a request path pass their own short budget.
    """
    _lock_impl(fd, timeout_s)


def unlock_file(fd: int) -> None:
    """Release the lock on the file descriptor."""
    _unlock_impl(fd)
