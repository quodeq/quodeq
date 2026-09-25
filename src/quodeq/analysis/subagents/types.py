"""Shared protocols for the subagent subsystem."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

# Default batch size for WorkQueue.take(). Shared with the concrete
# FileQueue implementation (analysis/subagents/file_queue.py) so the
# protocol's default and the implementation's default never drift apart.
DEFAULT_TAKE_COUNT = 5


@runtime_checkable
class WorkQueue(Protocol):
    """Interface for a work-distribution queue.

    ``FileQueue`` satisfies this protocol via structural subtyping.
    Alternative implementations (e.g. Redis-backed) can implement this
    protocol to plug into the same orchestration layer.
    """

    def take(self, count: int = DEFAULT_TAKE_COUNT, agent_id: str = "") -> list[str]:
        """Atomically remove and return the next *count* items."""
        ...

    def remaining(self) -> int:
        """Number of items still pending."""
        ...

    def taken_log(self) -> list[dict]:
        """Return the full take log for audit / crash recovery."""
        ...

    def all_taken_files(self) -> list[str]:
        """Return flat list of every file that was taken, in order."""
        ...
