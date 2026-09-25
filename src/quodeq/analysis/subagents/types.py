"""Shared protocols for the subagent subsystem."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

# Same default the MCP get_next_files tool hands out (analysis/mcp/schemas.py):
# one queue, one batch-size default, reused here so the protocol's default and
# the implementation's (FileQueue, analysis/subagents/file_queue.py) never
# drift apart. schemas.py imports only core, so this import is cycle-free.
from quodeq.analysis.mcp.schemas import DEFAULT_FILE_BATCH_SIZE


@runtime_checkable
class WorkQueue(Protocol):
    """Interface for a work-distribution queue.

    ``FileQueue`` satisfies this protocol via structural subtyping.
    Alternative implementations (e.g. Redis-backed) can implement this
    protocol to plug into the same orchestration layer.
    """

    def take(self, count: int = DEFAULT_FILE_BATCH_SIZE, agent_id: str = "") -> list[str]:
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
