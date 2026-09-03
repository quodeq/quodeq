from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.state_store import SQLiteStateStore


@dataclass(frozen=True)
class ProjectionResult:
    events_projected: int
    rebuilt: bool


@dataclass(frozen=True)
class _StalenessCheck:
    """What ``_detect_staleness`` found -- consumed by ``_apply_projection_deltas``."""

    events_changed: bool
    pre_pr1_db: bool
    actions_changed: bool
    actions_log: Path | None
    grades_stale: bool


class EnsureLockRegistry:
    """Per-run-dir locks serializing ``ensure_projected``.

    Entries are refcounted: a lock is created on first ``acquire()`` for a
    run_dir and removed once the last concurrent caller for that run_dir
    releases it. This bounds the registry to run_dirs CURRENTLY being
    projected, instead of growing one entry per run_dir ever seen for the
    life of a long-lived API/dashboard process. The default registry below
    is process-wide on purpose — concurrent callers projecting the same run
    must share one lock. Tests inject a fresh registry so lock state never
    leaks between them.
    """

    def __init__(self) -> None:
        self._locks: dict[Path, threading.Lock] = {}
        self._refcounts: dict[Path, int] = {}
        self._registry_lock = threading.Lock()

    @contextmanager
    def acquire(self, run_dir: Path) -> Iterator[None]:
        with self._registry_lock:
            lock = self._locks.get(run_dir)
            if lock is None:
                lock = threading.Lock()
                self._locks[run_dir] = lock
                self._refcounts[run_dir] = 0
            self._refcounts[run_dir] += 1
        lock.acquire()
        try:
            yield
        finally:
            lock.release()
            with self._registry_lock:
                self._refcounts[run_dir] -= 1
                if self._refcounts[run_dir] == 0:
                    del self._locks[run_dir]
                    del self._refcounts[run_dir]


_DEFAULT_LOCKS = EnsureLockRegistry()


class Projector:
    """Projects an Event Log into the State Store for a single Run.

    Owns the rebuild-vs-update decision: rebuilds when no checkpoint exists,
    updates incrementally otherwise. Raises on failure — callers decide how to
    surface it.
    """

    def __init__(
        self,
        engine: ProjectionEngine | None = None,
        store_factory: Callable[[Path], SQLiteStateStore] | None = None,
        locks: EnsureLockRegistry | None = None,
    ) -> None:
        self._engine = engine or ProjectionEngine()
        self._store_factory = store_factory or SQLiteStateStore
        self._locks = locks or _DEFAULT_LOCKS

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

        do_rebuild = force_rebuild or self._store_factory(run_dir).get_checkpoint() is None

        if do_rebuild:
            count = self._engine.rebuild(events_path, run_dir)
            return ProjectionResult(events_projected=count, rebuilt=True)
        else:
            count = self._engine.update(events_path, run_dir)
            return ProjectionResult(events_projected=count, rebuilt=False)

    def _detect_staleness(
        self,
        store: SQLiteStateStore,
        events_path: Path,
        project_dir: Path | None,
    ) -> _StalenessCheck:
        """Compare stored projection state against the on-disk event/action logs."""
        # Events.jsonl branch (today's behavior)
        projected_size = store.get_projected_size()
        current_size = events_path.stat().st_size
        events_changed = projected_size is None or projected_size != current_size

        # Pre-PR-1 DBs have a checkpoint (older code projected them) but no
        # ``projection_event_log_size`` key (added in PR 1). Their findings
        # may be missing columns the current mappers write (e.g. requirement).
        # Force a full rebuild on first contact so every column is correct.
        pre_pr1_db = projected_size is None and store.get_checkpoint() is not None

        # Actions.jsonl branch (new)
        actions_changed = False
        actions_log: Path | None = None
        if project_dir is not None:
            actions_log = project_dir / "actions.jsonl"
            last_actions_size = store.get_actions_projected_size() or 0
            current_actions_size = actions_log.stat().st_size if actions_log.is_file() else 0
            actions_changed = current_actions_size != last_actions_size

        # Grade tables embody the scoring math that computed them. When
        # that math changes (see GRADE_ALGO_VERSION), a run whose logs are
        # untouched still carries grades no fresh rescore would produce —
        # the same principle read differently depending on which screen's
        # read path served it. Re-derive from the already-projected
        # findings; no event replay needed.
        from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION  # noqa: PLC0415
        grades_stale = store.get_grades_algo_version() != GRADE_ALGO_VERSION

        return _StalenessCheck(
            events_changed=events_changed,
            pre_pr1_db=pre_pr1_db,
            actions_changed=actions_changed,
            actions_log=actions_log,
            grades_stale=grades_stale,
        )

    def _apply_projection_deltas(
        self,
        events_path: Path,
        run_dir: Path,
        staleness: _StalenessCheck,
    ) -> ProjectionResult:
        """Project events, then actions, then recompute grades -- in that order.

        Order matters: events must land before action events touch them, and
        action-replay is forced when events changed so brand-new findings get
        matched against pre-existing dismissals.
        """
        # Project events first (so new findings exist before action events touch them).
        if staleness.events_changed:
            result = self.project(events_path, run_dir, force_rebuild=staleness.pre_pr1_db)
        else:
            result = ProjectionResult(events_projected=0, rebuilt=False)

        # Project actions. If events changed too, force-replay so brand-new findings
        # get matched against pre-existing dismissals.
        if staleness.actions_log is not None and (staleness.actions_changed or staleness.events_changed):
            self._engine.update_actions(
                staleness.actions_log, run_dir, force=staleness.events_changed,
            )

        # Grade tables are derived from findings + dismissals. Recompute
        # whenever either source changed, or when the stored grades were
        # computed with an older version of the math (recompute_grades
        # stamps the current one).
        if staleness.events_changed or staleness.actions_changed or staleness.grades_stale:
            from quodeq.data.projection.grade_projector import recompute_grades  # noqa: PLC0415
            recompute_grades(run_dir)

        return result

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

        with self._locks.acquire(run_dir):
            if project_dir is not None:
                from quodeq.data.migrations.dismissed_json_to_actions_log import (  # noqa: PLC0415
                    migrate_if_needed,
                )
                migrate_if_needed(project_dir)
            store = self._store_factory(run_dir)

            staleness = self._detect_staleness(store, events_path, project_dir)

            if not staleness.events_changed and not staleness.actions_changed and not staleness.grades_stale:
                return ProjectionResult(events_projected=0, rebuilt=False)

            return self._apply_projection_deltas(events_path, run_dir, staleness)
