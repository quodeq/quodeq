from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.state_store import SQLiteStateStore


@dataclass(frozen=True)
class ProjectionResult:
    events_projected: int
    rebuilt: bool


_ensure_locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)


class Projector:
    """Projects an Event Log into the State Store for a single Run.

    Owns the rebuild-vs-update decision: rebuilds when no checkpoint exists,
    updates incrementally otherwise. Raises on failure — callers decide how to
    surface it.
    """

    def __init__(self, engine: ProjectionEngine | None = None) -> None:
        self._engine = engine or ProjectionEngine()

    def project(
        self,
        events_path: Path,
        run_dir: Path,
        *,
        force_rebuild: bool = False,
    ) -> ProjectionResult:
        """Project *events_path* into the State Store at *run_dir*.

        Raises ``FileNotFoundError`` when *events_path* does not exist.
        Any other projection failure propagates to the caller.
        """
        if not events_path.is_file():
            raise FileNotFoundError(f"Event log not found: {events_path}")

        do_rebuild = force_rebuild or SQLiteStateStore(run_dir).get_checkpoint() is None

        if do_rebuild:
            count = self._engine.rebuild(events_path, run_dir)
            return ProjectionResult(events_projected=count, rebuilt=True)
        else:
            count = self._engine.update(events_path, run_dir)
            return ProjectionResult(events_projected=count, rebuilt=False)

    def ensure_projected(self, events_path: Path, run_dir: Path) -> ProjectionResult:
        """Fast no-op if State Store is fresh; otherwise project incrementally.

        Compares the Event Log's byte size to the last projected size stored
        in run_meta. The Event Log is append-only, so size monotonicity makes
        this race-free for the single-process case. An in-process lock per
        run_dir prevents concurrent reads from double-projecting.
        """
        if not events_path.is_file():
            raise FileNotFoundError(f"Event log not found: {events_path}")

        with _ensure_locks[run_dir]:
            store = SQLiteStateStore(run_dir)
            projected_size = store.get_projected_size()
            current_size = events_path.stat().st_size
            if projected_size is not None and projected_size == current_size:
                return ProjectionResult(events_projected=0, rebuilt=False)
            return self.project(events_path, run_dir)
