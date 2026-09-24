"""Queue state persistence: atomic JSON read/write with file locking.

Internal module — use ``FileQueue`` from ``file_queue.py`` instead.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from quodeq.analysis.subagents._file_lock import lock_file, unlock_file


QUEUE_VERSION = 1

_LOCK_FILE_MODE = 0o600

_log = logging.getLogger(__name__)


class FileQueueError(RuntimeError):
    """Raised on queue corruption or I/O failures."""


@contextmanager
def locked(lock_path: Path):
    """Exclusive file lock via a separate .lock file.

    The lock file is never deleted — it's harmless and avoids races
    where one process unlinks it while another is about to lock it.
    """
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, _LOCK_FILE_MODE)
    locked_ok = False
    try:
        lock_file(fd)
        locked_ok = True
        yield
    finally:
        if locked_ok:
            unlock_file(fd)
        os.close(fd)


def read_state(path: Path) -> dict:
    """Read and validate the queue JSON file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileQueueError(f"Cannot read queue file: {exc}") from exc
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FileQueueError(f"Queue file is corrupted: {exc}") from exc
    version = state.get("version")
    if version != QUEUE_VERSION:
        raise FileQueueError(f"Unsupported queue version: {version} (expected {QUEUE_VERSION})")
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
        with os.fdopen(fd, "w", encoding="utf-8") as f:
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
            except OSError as exc:
                _log.debug("temp queue state file not removed after a failed write: %s", exc)
