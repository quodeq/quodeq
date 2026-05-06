"""Queue state persistence: atomic JSON read/write with file locking.

Internal module — use ``FileQueue`` from ``file_queue.py`` instead.

The filesystem implementation below satisfies ``QueueStateProtocol``.
To swap in a different backend (e.g. Redis, database), implement that
protocol and pass your instance where ``read_state``/``write_state`` are
called.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, runtime_checkable

import time as _time

from quodeq.analysis.subagents._file_lock import lock_file, unlock_file


@runtime_checkable
class QueueStateProtocol(Protocol):
    """Abstraction for queue state storage.

    The default implementation uses the filesystem (``read_state`` /
    ``write_state`` module functions).  Implement this protocol to back
    the queue with a different storage layer.
    """

    def read(self, path: Path) -> dict: ...
    def write(self, state: dict, path: Path) -> None: ...

_QUEUE_VERSION = 1

_LOCK_FILE_MODE = 0o600
_STALE_LOCK_THRESHOLD_SECS = 60

_log = logging.getLogger(__name__)


class FileQueueError(RuntimeError):
    """Raised on queue corruption or I/O failures."""


def cleanup_stale_lock(lock_path: Path, threshold: float = _STALE_LOCK_THRESHOLD_SECS) -> bool:
    """Remove a stale lock file if it exists and is older than *threshold* seconds.

    Returns ``True`` if a stale lock was removed.  This is a defensive measure
    for environments where ``flock`` may not release properly (e.g. networked
    file-systems) or where the lock file was left behind by a hard crash.
    """
    try:
        stat = lock_path.stat()
    except FileNotFoundError:
        return False

    age = _time.time() - stat.st_mtime
    if age > threshold:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass  # another process already cleaned it up
        _log.debug(
            "Removed stale lock file %s (age=%.1fs, threshold=%.0fs)",
            lock_path, age, threshold,
        )
        return True
    return False


@contextmanager
def locked(lock_path: Path):
    """Exclusive file lock via a separate .lock file.

    The lock file is never deleted — it's harmless and avoids races
    where one process unlinks it while another is about to lock it.
    """
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, _LOCK_FILE_MODE)
    try:
        lock_file(fd)
        yield
    finally:
        unlock_file(fd)
        os.close(fd)


def read_state(path: Path) -> dict:
    """Read and validate the queue JSON file."""
    try:
        raw = path.read_text()
    except OSError as exc:
        raise FileQueueError(f"Cannot read queue file: {exc}") from exc
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FileQueueError(f"Queue file is corrupted: {exc}") from exc
    version = state.get("version")
    if version != _QUEUE_VERSION:
        raise FileQueueError(f"Unsupported queue version: {version} (expected {_QUEUE_VERSION})")
    if not isinstance(state.get("pending"), list):
        raise FileQueueError("Queue file missing 'pending' list")
    if not isinstance(state.get("taken"), list):
        raise FileQueueError("Queue file missing 'taken' list")
    return state


def write_state(state: dict, path: Path) -> None:
    """Atomic write: temp file in the same directory, then rename.

    Uses try/finally with a sentinel so cleanup runs on any exit path —
    including SIGINT/SystemExit — without swallowing those signals.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp", prefix=".queue_")
    cleanup_tmp: str | None = tmp_path
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        # os.replace is atomic and overwrites on all platforms;
        # os.rename raises FileExistsError on Windows when the destination exists.
        os.replace(tmp_path, str(path))
        cleanup_tmp = None  # ownership transferred to final path
    finally:
        if cleanup_tmp is not None:
            try:
                os.unlink(cleanup_tmp)
            except OSError:
                pass
