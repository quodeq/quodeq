from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.state_store import SQLiteStateStore


@dataclass(frozen=True)
class ProjectionResult:
    events_projected: int
    rebuilt: bool


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
