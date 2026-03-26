"""Platform-specific file locking helpers.

Provides ``lock_file`` and ``unlock_file`` that dispatch to the correct
OS primitive (``fcntl`` on Unix, ``msvcrt`` on Windows).
"""
from __future__ import annotations

import sys


def _make_lock_ops() -> tuple:
    """Return (lock_fn, unlock_fn) for the current platform."""
    if sys.platform == "win32":
        import msvcrt
        def _lock(fd: int) -> None:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        def _unlock(fd: int) -> None:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        def _lock(fd: int) -> None:
            fcntl.flock(fd, fcntl.LOCK_EX)
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
