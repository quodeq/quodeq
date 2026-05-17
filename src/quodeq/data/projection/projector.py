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

    def ensure_projected(
        self,
        events_path: Path,
        run_dir: Path,
        *,
        project_dir: Path | None = None,
    ) -> ProjectionResult:
        """Fast no-op if both event and action logs are fresh; else project deltas."""
        if not events_path.is_file():
            raise FileNotFoundError(f"Event log not found: {events_path}")

        with _ensure_locks[run_dir]:
            store = SQLiteStateStore(run_dir)

            # Events.jsonl branch (today's behavior)
            projected_size = store.get_projected_size()
            current_size = events_path.stat().st_size
            events_changed = projected_size is None or projected_size != current_size

            # Actions.jsonl branch (new)
            actions_changed = False
            actions_log: Path | None = None
            if project_dir is not None:
                actions_log = project_dir / "actions.jsonl"
                last_actions_size = store.get_actions_projected_size() or 0
                current_actions_size = actions_log.stat().st_size if actions_log.is_file() else 0
                actions_changed = current_actions_size != last_actions_size

            if not events_changed and not actions_changed:
                return ProjectionResult(events_projected=0, rebuilt=False)

            # Project events first (so new findings exist before action events touch them).
            if events_changed:
                result = self.project(events_path, run_dir)
            else:
                result = ProjectionResult(events_projected=0, rebuilt=False)

            # Project actions. If events changed too, force-replay so brand-new findings
            # get matched against pre-existing dismissals.
            if actions_log is not None and (actions_changed or events_changed):
                self._engine.update_actions(actions_log, run_dir, force=events_changed)

            return result
