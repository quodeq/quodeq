from __future__ import annotations

import sys
from typing import IO, Protocol


class FileLock(Protocol):
    def acquire(self, f: IO) -> None: ...
    def release(self, f: IO) -> None: ...


if sys.platform == "win32":
    import msvcrt

    class _WindowsFileLock:
        def acquire(self, f: IO) -> None:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

        def release(self, f: IO) -> None:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def get_file_lock() -> FileLock:
        return _WindowsFileLock()

else:
    import fcntl

    class _UnixFileLock:
        def acquire(self, f: IO) -> None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)

        def release(self, f: IO) -> None:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def get_file_lock() -> FileLock:
        return _UnixFileLock()
