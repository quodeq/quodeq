"""Platform-specific file locking helpers.

Provides ``lock_file`` and ``unlock_file`` that dispatch to the correct
OS primitive (``fcntl`` on Unix, ``msvcrt`` on Windows).

Lives in core (stdlib-only, no outward imports) so any layer can use it
without reaching into ``data/``. ``data/_file_lock.py`` re-exports it for
the rest of the codebase.
"""
from __future__ import annotations

import logging
import sys
import time

_logger = logging.getLogger(__name__)

# Windows blocking lock budget. msvcrt.LK_LOCK only retries 10x at 1s,
# which is too short under the subagent pool's heavy contention. We use
# the non-blocking variant in our own retry loop instead.
_WIN_LOCK_TIMEOUT_S = 60.0
_WIN_LOCK_RETRY_INTERVAL_S = 0.05

# Unix flock has no built-in timeout; poll with a short non-blocking retry
# loop instead, mirroring the Windows branch's budget and cadence.
_UNIX_LOCK_TIMEOUT_S = 60.0
_UNIX_LOCK_RETRY_INTERVAL_S = 0.05


def _make_lock_ops() -> tuple:
    """Return (lock_fn, unlock_fn) for the current platform."""
    if sys.platform == "win32":
        import msvcrt
        def _lock(fd: int, timeout_s: float | None = None) -> None:
            # Read at call time, not as a default arg: tests monkeypatch the
            # module constant to keep the contention case fast.
            if timeout_s is None:
                timeout_s = _WIN_LOCK_TIMEOUT_S
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(_WIN_LOCK_RETRY_INTERVAL_S)
        def _unlock(fd: int) -> None:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        def _lock(fd: int, timeout_s: float | None = None) -> None:
            # Read at call time, not as a default arg: tests monkeypatch the
            # module constant to keep the contention case fast.
            if timeout_s is None:
                timeout_s = _UNIX_LOCK_TIMEOUT_S
            _logger.debug(
                "Waiting for file lock (timeout %.0fs)", timeout_s,
            )
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        _logger.warning(
                            "Timed out after %.0fs waiting for file lock", timeout_s,
                        )
                        raise TimeoutError(
                            f"Timed out waiting for file lock after {timeout_s}s",
                        ) from None
                    time.sleep(_UNIX_LOCK_RETRY_INTERVAL_S)
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
