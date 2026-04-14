"""Cross-process file queue for distributing work across subagents.

See ``_queue_state`` for the atomic JSON persistence layer.
"""
from __future__ import annotations

import time
from pathlib import Path

from quodeq.analysis.subagents._queue_state import (
    FileQueueError,  # noqa: F401 — re-export
    _QUEUE_VERSION,
    cleanup_stale_lock,
    locked,
    read_state,
    write_state,
)
from quodeq.analysis.subagents.types import WorkQueue  # noqa: F401 — re-export


class FileQueue:
    """Distributes files across N subagent processes via a locked JSON file.

    Atomic writes, exclusive locking, and a take log ensure no file is lost.
    For multi-machine deployments, implement ``WorkQueue`` with a networked backend.
    """

    def __init__(
        self, queue_path: Path, files: list[str] | None = None,
        max_files_per_agent: int = 0,
    ):
        self._path = Path(queue_path)
        self._lock_path = self._path.with_suffix(".lock")
        cleanup_stale_lock(self._lock_path)

        if files is not None:
            state: dict = {"version": _QUEUE_VERSION, "pending": list(files), "taken": []}
            if max_files_per_agent > 0:
                state["max_files_per_agent"] = max_files_per_agent
            write_state(state, self._path)
        elif not self._path.exists():
            raise FileQueueError(
                f"Queue file not found: {self._path}. "
                f"Initialize the queue by passing a file list to the FileQueue constructor."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def take(self, count: int = 5, agent_id: str = "") -> list[str]:
        """Atomically remove and return the next *count* files.

        Example::

            queue = FileQueue(Path("/tmp/queue.json"), files=["a.py", "b.py"])
            batch = queue.take(count=2, agent_id="agent-1")
        """
        if count < 1:
            return []
        with locked(self._lock_path):
            state = read_state(self._path)

            max_per_agent = state.get("max_files_per_agent", 0)
            if max_per_agent > 0 and agent_id:
                agent_totals = state.get("agent_totals", {})
                agent_total = agent_totals.get(agent_id, 0)
                remaining_budget = max_per_agent - agent_total
                if remaining_budget <= 0:
                    return []
                count = min(count, remaining_budget)

            pending = state["pending"]
            batch = pending[:count]
            if not batch:
                return []
            state["pending"] = pending[count:]
            state["taken"].append({
                "files": batch, "agent": agent_id, "ts": time.time(),
            })
            if agent_id:
                totals = state.setdefault("agent_totals", {})
                totals[agent_id] = totals.get(agent_id, 0) + len(batch)
            write_state(state, self._path)
        return batch

    def remaining(self) -> int:
        """Number of files still pending in the queue.

        Example::

            remaining = queue.remaining()  # e.g. 42
        """
        with locked(self._lock_path):
            return len(read_state(self._path)["pending"])

    def stats(self) -> tuple[int, int]:
        """Return (remaining, taken) counts in a single file read.

        Example::

            remaining, taken = queue.stats()
        """
        with locked(self._lock_path):
            state = read_state(self._path)
        taken = sum(len(e["files"]) for e in state["taken"])
        return len(state["pending"]), taken

    def taken_log(self) -> list[dict]:
        """Return the full take log for audit / crash recovery.

        Example::

            log = queue.taken_log()  # [{"files": [...], "agent": "a1", "ts": ...}, ...]
        """
        with locked(self._lock_path):
            return list(read_state(self._path)["taken"])

    def all_taken_files(self) -> list[str]:
        """Return flat list of every file that was taken, in order.

        Example::

            files = queue.all_taken_files()  # ["a.py", "b.py", ...]
        """
        result: list[str] = []
        for entry in self.taken_log():
            result.extend(entry["files"])
        return result
