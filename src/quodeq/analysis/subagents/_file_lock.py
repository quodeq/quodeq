"""Platform-specific file locking helpers.

Provides ``lock_file`` and ``unlock_file`` that dispatch to the correct
OS primitive (``fcntl`` on Unix, ``msvcrt`` on Windows).
"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    import msvcrt as _lock_mod
else:
    import fcntl as _lock_mod  # type: ignore[no-redef]


def lock_file(fd: int) -> None:
    """Acquire an exclusive lock on the file descriptor."""
    if sys.platform == "win32":
        _lock_mod.locking(fd, _lock_mod.LK_LOCK, 1)
    else:
        _lock_mod.flock(fd, _lock_mod.LOCK_EX)


def unlock_file(fd: int) -> None:
    """Release the lock on the file descriptor."""
    if sys.platform == "win32":
        _lock_mod.locking(fd, _lock_mod.LK_UNLCK, 1)
    else:
        _lock_mod.flock(fd, _lock_mod.LOCK_UN)
