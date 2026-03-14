"""Cross-process file queue for distributing work across subagents.

Backed by a JSON file with atomic writes (write-to-temp + rename).
Cross-process safe via file locking (fcntl on Unix, msvcrt on Windows).
Maintains a take log so no file is silently lost.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

_QUEUE_VERSION = 1


class FileQueueError(RuntimeError):
    """Raised on queue corruption or I/O failures."""


class FileQueue:
    """Distributes files across N subagent processes.

    The queue state lives in a JSON file::

        {
            "version": 1,
            "pending": ["file1.py", "file2.py", ...],
            "taken": [
                {"files": ["file3.py"], "agent": "agent-0", "ts": 1710000000.0},
                ...
            ]
        }

    Safety guarantees:

    - **Atomic writes**: state is written to a temp file then renamed, so a
      crash mid-write never corrupts the queue.
    - **Exclusive locking**: a separate ``.lock`` file serialises all access
      via ``fcntl.flock``.  The OS releases the lock automatically if the
      holding process dies.
    - **Take log**: every ``take()`` is recorded with agent id and timestamp,
      so files can be accounted for even after a crash.
    """

    def __init__(self, queue_path: Path, files: list[str] | None = None):
        """Create or open a file queue.

        Args:
            queue_path: Path to the queue JSON file.
            files: If provided, initialise the queue with this file list.
                   If *None*, the queue must already exist on disk.

        Raises:
            FileQueueError: If *files* is None and the queue file doesn't exist.
        """
        self._path = Path(queue_path)
        self._lock_path = self._path.with_suffix(".lock")

        if files is not None:
            self._write_state({"version": _QUEUE_VERSION, "pending": list(files), "taken": []})
        elif not self._path.exists():
            raise FileQueueError(f"Queue file not found: {self._path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def take(self, count: int = 5, agent_id: str = "") -> list[str]:
        """Atomically remove and return the next *count* files.

        Returns an empty list when the queue is drained.
        """
        if count < 1:
            return []
        with self._locked():
            state = self._read_state()
            pending = state["pending"]
            batch = pending[:count]
            if not batch:
                return []
            state["pending"] = pending[count:]
            state["taken"].append({
                "files": batch,
                "agent": agent_id,
                "ts": time.time(),
            })
            self._write_state(state)
        return batch

    def remaining(self) -> int:
        """Number of files still pending in the queue."""
        with self._locked():
            state = self._read_state()
        return len(state["pending"])

    def taken_log(self) -> list[dict]:
        """Return the full take log for audit / crash recovery."""
        with self._locked():
            state = self._read_state()
        return list(state["taken"])

    def all_taken_files(self) -> list[str]:
        """Return flat list of every file that was taken, in order."""
        result: list[str] = []
        for entry in self.taken_log():
            result.extend(entry["files"])
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @contextmanager
    def _locked(self):
        """Exclusive file lock via a separate .lock file.

        The lock file is never deleted — it's harmless and avoids races
        where one process unlinks it while another is about to lock it.
        """
        fd = os.open(str(self._lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read_state(self) -> dict:
        """Read and validate the queue JSON file."""
        try:
            raw = self._path.read_text()
        except OSError as exc:
            raise FileQueueError(f"Cannot read queue file: {exc}") from exc
        try:
            state = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FileQueueError(f"Queue file is corrupted: {exc}") from exc
        if not isinstance(state.get("pending"), list):
            raise FileQueueError("Queue file missing 'pending' list")
        if not isinstance(state.get("taken"), list):
            raise FileQueueError("Queue file missing 'taken' list")
        return state

    def _write_state(self, state: dict) -> None:
        """Atomic write: temp file in the same directory, then rename."""
        parent = self._path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(parent), suffix=".tmp", prefix=".queue_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, str(self._path))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
