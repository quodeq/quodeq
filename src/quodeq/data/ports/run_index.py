"""Protocol for the global run-metadata index (immutable fields only)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class IndexedRun:
    project: str
    run_id: str
    branch: str | None
    model: str | None
    started_at: str
    finished_at: str | None
    state: str
    db_path: str


@runtime_checkable
class RunIndex(Protocol):
    def record_started(
        self, *, project: str, run_id: str, branch: str | None,
        model: str | None, started_at: str, db_path: str,
    ) -> None: ...

    def record_finished(
        self, *, project: str, run_id: str, finished_at: str, state: str,
    ) -> None: ...

    def list_runs(self, *, project: str | None = None, limit: int = 100) -> list[IndexedRun]: ...
