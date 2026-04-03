"""Queue state persistence: atomic JSON read/write with file locking.

Internal module — use ``FileQueue`` from ``file_queue.py`` instead.
"""
from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from quodeq.analysis.subagents._file_lock import lock_file, unlock_file

_QUEUE_VERSION = 1


class FileQueueError(RuntimeError):
    """Raised on queue corruption or I/O failures."""


@contextmanager
def locked(lock_path: Path):
    """Exclusive file lock via a separate .lock file.

    The lock file is never deleted — it's harmless and avoids races
    where one process unlinks it while another is about to lock it.
    """
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
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
    """Atomic write: temp file in the same directory, then rename."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp", prefix=".queue_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, str(path))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
