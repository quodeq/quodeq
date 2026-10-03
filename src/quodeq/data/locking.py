"""Cross-platform advisory locking on an open file handle."""
from __future__ import annotations

import sys
from typing import IO, Protocol

from quodeq.data.file_lock import lock_file, unlock_file
from quodeq.shared.constants import PLATFORM_WIN32


class FileLock(Protocol):
    """Exclusive whole-file lock held for the lifetime of a critical section."""

    def acquire(self, f: IO) -> None:
        """Wait until this process owns the lock on *f*.

        Raises ``OSError`` (``TimeoutError`` on POSIX) once the lock budget
        in ``core/utils/file_lock.py`` runs out.
        """
        ...

    def release(self, f: IO) -> None:
        """Drop the lock on *f*. Undefined if the caller never acquired it."""
        ...


if sys.platform == PLATFORM_WIN32:
    class _WindowsFileLock:
        def acquire(self, f: IO) -> None:
            f.seek(0)
            lock_file(f.fileno())

        def release(self, f: IO) -> None:
            f.seek(0)
            unlock_file(f.fileno())

    def get_file_lock() -> FileLock:
        """Return the ``msvcrt.locking`` implementation used on Windows.

        Only the first byte of the file is locked, which is enough because
        every caller goes through this same helper.
        """
        return _WindowsFileLock()

else:
    class _UnixFileLock:
        def acquire(self, f: IO) -> None:
            lock_file(f.fileno())

        def release(self, f: IO) -> None:
            unlock_file(f.fileno())

    def get_file_lock() -> FileLock:
        """Return the ``flock`` implementation used everywhere except Windows."""
        return _UnixFileLock()
