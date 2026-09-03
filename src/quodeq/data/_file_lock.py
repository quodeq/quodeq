"""Platform-specific file locking helpers.

Provides ``lock_file`` and ``unlock_file`` that dispatch to the correct
OS primitive (``fcntl`` on Unix, ``msvcrt`` on Windows).

Kept in the data layer as a small, self-contained infrastructure utility
used by the subagent pool via ``analysis.subagents._file_lock``.
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
        def _lock(fd: int) -> None:
            deadline = time.monotonic() + _WIN_LOCK_TIMEOUT_S
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
        def _lock(fd: int) -> None:
            _logger.debug(
                "Waiting for file lock (timeout %.0fs)", _UNIX_LOCK_TIMEOUT_S,
            )
            deadline = time.monotonic() + _UNIX_LOCK_TIMEOUT_S
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except OSError:
                    if time.monotonic() >= deadline:
                        _logger.warning(
                            "Timed out after %.0fs waiting for file lock",
                            _UNIX_LOCK_TIMEOUT_S,
                        )
                        raise TimeoutError(
                            f"Timed out waiting for file lock after {_UNIX_LOCK_TIMEOUT_S}s",
                        ) from None
                    time.sleep(_UNIX_LOCK_RETRY_INTERVAL_S)
        def _unlock(fd: int) -> None:
            fcntl.flock(fd, fcntl.LOCK_UN)
    return _lock, _unlock


_lock_impl, _unlock_impl = _make_lock_ops()


def lock_file(fd: int) -> None:
    """Acquire an exclusive lock on the file descriptor."""
    _lock_impl(fd)


def unlock_file(fd: int) -> None:
    """Release the lock on the file descriptor."""
    _unlock_impl(fd)
