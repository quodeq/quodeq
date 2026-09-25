"""Cross-platform advisory locking on an open file handle."""
from __future__ import annotations

import sys
from typing import IO, Protocol

from quodeq.shared.constants import PLATFORM_WIN32


class FileLock(Protocol):
    """Exclusive whole-file lock held for the lifetime of a critical section."""

    def acquire(self, f: IO) -> None:
        """Block until this process owns the lock on *f*."""
        ...

    def release(self, f: IO) -> None:
        """Drop the lock on *f*. Undefined if the caller never acquired it."""
        ...


if sys.platform == PLATFORM_WIN32:
    import msvcrt

    class _WindowsFileLock:
        def acquire(self, f: IO) -> None:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

        def release(self, f: IO) -> None:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def get_file_lock() -> FileLock:
        """Return the ``msvcrt.locking`` implementation used on Windows.

        Only the first byte of the file is locked, which is enough because
        every caller goes through this same helper.
        """
        return _WindowsFileLock()

else:
    import fcntl

    class _UnixFileLock:
        def acquire(self, f: IO) -> None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

        def release(self, f: IO) -> None:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def get_file_lock() -> FileLock:
        """Return the ``flock`` implementation used everywhere except Windows."""
        return _UnixFileLock()
