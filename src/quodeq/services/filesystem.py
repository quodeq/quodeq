"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import ProjectEntry, ViolationSummary, to_camel_dict
from quodeq.core.types.job import JobSnapshot
from quodeq.services import _fs_clone, _fs_projects, _fs_reports
from quodeq.services import run_index as _run_index
from quodeq.services.base import ActionProvider
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.jobs import JobManager
from quodeq.services.tooling_mixin import FsToolingMixin

_PROJECT_CACHE_TTL_S = 5  # seconds before project list is re-read


class FilesystemActionProvider(FsEvaluationMixin, FsToolingMixin, ActionProvider):
    """Filesystem-backed action provider.

    This class uses cooperative multiple inheritance via **mixins** to compose
    orthogonal capabilities without code duplication:

    * ``FsEvaluationMixin`` -- evaluation lifecycle (start, status, cancel).
    * ``FsToolingMixin``    -- AI-client discovery and repo browsing.
    * ``ActionProvider``    -- abstract base defining the provider contract.

    The mixins are stateless mix-in classes (no ``__init__``, no instance
    state of their own) and do not form a diamond; they are combined here
    purely for composition.
    """

    def __init__(
        self,
        job_manager: JobManager | None = None,
        compiled_dir: Path | None = None,
        index_db_path: Path | None = None,
        reports_root: Path | None = None,
    ) -> None:
        super().__init__()
        self._reports_root = reports_root
        self._jobs = job_manager or JobManager(reports_root=reports_root)
        self._compiled_dir = compiled_dir
        self._index_db_path = Path(index_db_path) if index_db_path is not None else None
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }
        self._project_cache: dict[str, Any] | None = None
        self._project_cache_time: float = 0

    # -- index helpers --------------------------------------------------

    def _open_index(self):
        """Open (lazily) the index DB. Resolved from init kwarg or env."""
        if self._index_db_path is None:
            from quodeq.shared._env import get_index_db_path
            self._index_db_path = Path(get_index_db_path())
        return _run_index.open_index(self._index_db_path)

    def list_evaluations(self, limit: int = 0, reports_dir: Path | None = None) -> list[JobSnapshot]:
        """Return runs from the SQLite index merged with in-memory JobManager jobs."""
        if reports_dir is None:
            from quodeq.shared._env import get_evaluations_dir
            reports_dir = Path(get_evaluations_dir())
        else:
            reports_dir = Path(reports_dir)
        db = self._open_index()
        try:
            _run_index.sync_index(db, reports_dir)
            rows = _run_index.list_runs(db, limit=0)  # fetch all, merge, then limit
        finally:
            db.close()
        snapshots = [self._run_row_to_snapshot(r) for r in rows]
        # Merge in-memory dashboard-spawned jobs (JobManager).
        # Only non-external (internally spawned) jobs override the index; external
        # heuristics from find_external_runs may be stale and the index wins there.
        try:
            internal_jobs = self._jobs.list_jobs(reports_root=None)  # no external heuristic
        except (AttributeError, TypeError):
            internal_jobs = []
        by_id = {s.job_id: s for s in snapshots}
        for j in internal_jobs:
            by_id[j.job_id] = j  # internal dashboard-spawned jobs always take priority
        merged = list(by_id.values())
        merged.sort(key=lambda s: s.started_at or "", reverse=True)
        return merged[:limit] if limit and limit > 0 else merged

    def get_evaluation_status(self, job_id: str, reports_dir: Path | None = None) -> JobSnapshot | None:
        """Return a single run's snapshot.

        For internal (non-ext) job_ids, JobManager is the authoritative in-memory
        store. For ext- job_ids (external/CLI runs), the SQLite index is
        authoritative — route there directly and run the scoped sync so stale
        runs get promoted to cancelled on this request.
        """
        # Internal job_ids: live dashboard-spawned — JobManager's in-memory state wins.
        if not job_id.startswith("ext-"):
            try:
                internal = self._jobs.get_job(job_id, reports_root=None) if hasattr(self._jobs, "get_job") else None
            except TypeError:
                internal = None
            if internal is not None:
                return internal

        # ext- job_ids (and any internal ID we didn't find in memory): go to the index.
        if reports_dir is None:
            from quodeq.shared._env import get_evaluations_dir
            reports_dir = Path(get_evaluations_dir())
        else:
            reports_dir = Path(reports_dir)
        db = self._open_index()
        try:
            # Scoped sync: only walk the target run_dir if we can resolve it.
            if job_id.startswith("ext-"):
                run_id = job_id[len("ext-"):]
                # Search for this run across all projects (same pattern as legacy code).
                for project_dir in (reports_dir.iterdir() if reports_dir.is_dir() else []):
                    candidate = project_dir / run_id
                    if candidate.is_dir():
                        _run_index.sync_index_for_run(db, candidate)
                        break
                else:
                    # Fall back to full sync so legacy runs are synthesized too.
                    _run_index.sync_index(db, reports_dir)
            else:
                _run_index.sync_index(db, reports_dir)
            row = _run_index.get_run(db, job_id)
        finally:
            db.close()
        if row is None:
            return None
        return self._run_row_to_snapshot(row)

    @staticmethod
    def _run_row_to_snapshot(row: "_run_index.RunRow") -> JobSnapshot:
        return JobSnapshot(
            job_id=row.job_id,
            status=row.state,
            command="",
            started_at=row.started_at,
            ended_at=row.finalized_at,
            exit_code=None,
            logs=[],
            output_project=row.project_uuid,
            output_run_id=row.run_id,
            phase=row.phase,
            current_dimension=row.current_dimension,
            dimensions=None,
            error=row.exit_reason,
            source="external" if row.job_id.startswith("ext-") else "internal",
            exit_reason=row.exit_reason,
        )

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _build_project_list(reports_root: Path) -> list[ProjectEntry]:
        return _fs_projects.build_project_list(reports_root)

    def _is_cache_valid(self) -> bool:
        return self._project_cache is not None and (time.monotonic() - self._project_cache_time) < _PROJECT_CACHE_TTL_S

    # -- project CRUD (delegates to _fs_projects) -----------------------

    def list_projects(self, reports_dir: str) -> dict[str, Any]:
        if self._is_cache_valid():
            return self._project_cache  # type: ignore[return-value]
        projects = _fs_projects.build_project_list(Path(reports_dir))
        result = {"projects": [to_camel_dict(p) for p in projects]}
        self._project_cache = result
        self._project_cache_time = time.monotonic()
        return result

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        return _fs_projects.update_project_path(reports_dir, project, new_path)

    def delete_project(self, reports_dir: str, project: str) -> bool:
        return _fs_projects.delete_project(reports_dir, project)

    def clone_to_local(self, reports_dir: str, project: str, destination: str) -> dict[str, Any] | None:
        # Validate destination: must be absolute and free of traversal components.
        dest = Path(destination)
        if not dest.is_absolute() or ".." in dest.parts:
            return None
        return _fs_clone.clone_to_local(
            reports_dir, project, destination, get_project_info_fn=self.get_project_info,
        )

    def get_project_info(self, reports_dir: str, project: str) -> dict[str, Any] | None:
        return _fs_projects.get_project_info(reports_dir, project)

    # -- reports / dashboard (delegates to _fs_reports) -----------------

    def get_dashboard(self, reports_dir: str, project: str, run: str) -> dict[str, Any]:
        return _fs_reports.get_dashboard(reports_dir, project, run)

    def get_accumulated(self, reports_dir: str, project: str, as_of: str | None) -> dict[str, Any] | None:
        return _fs_reports.get_accumulated(reports_dir, project, as_of)

    def get_dimension_eval(self, reports_dir: str, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
        return _fs_reports.get_dimension_eval(
            reports_dir, project, run_id, dimension, compiled_dir=self._compiled_dir,
        )

    def get_violations(self, reports_dir: str, project: str, run_id: str) -> ViolationSummary:
        return _fs_reports.get_violations(reports_dir, project, run_id)

    def _resolve_reports_root(self) -> Path | None:
        """Return the active reports directory.

        Prefers the per-instance root set at construction time; falls back to
        the ``QUODEQ_EVALUATIONS_DIR`` environment variable so that the default
        provider (constructed with no arguments) still resolves paths correctly
        at runtime.
        """
        if self._reports_root is not None:
            return Path(self._reports_root)
        try:
            from quodeq.shared.utils import get_evaluations_dir
            return Path(get_evaluations_dir())
        except Exception:
            return None

    def get_log_run_dir(self, job_id: str) -> Path | None:
        """Return the run_dir for *job_id*, or None if unknown.

        Handles both internal JobManager ids and 'ext-<run_id>' external ids.
        """
        if job_id.startswith("ext-"):
            run_id = job_id[len("ext-"):]
            reports_root = self._resolve_reports_root()
            if reports_root is None or not reports_root.is_dir():
                return None
            for project_dir in reports_root.iterdir():
                if not project_dir.is_dir():
                    continue
                candidate = project_dir / run_id
                if candidate.is_dir():
                    return candidate
            return None
        # Internal: look up job in the store (returns Job with output fields)
        job = self._jobs._store.get(job_id)
        if job is None or job.output_project is None or job.output_run_id is None:
            return None
        reports_root = self._resolve_reports_root()
        if reports_root is None:
            return None
        return reports_root / job.output_project / job.output_run_id

    def is_job_complete(self, job_id: str) -> bool:
        """Return True if *job_id* has reached a terminal state."""
        if job_id.startswith("ext-"):
            run_dir = self.get_log_run_dir(job_id)
            if run_dir is None:
                return False
            if (run_dir / "scan.json").exists():
                return True
            # Stale detection: no scan.json AND no live PID -> treat as complete.
            from quodeq.services._external_jobs import _pid_liveness
            return not _pid_liveness(run_dir)
        job = self._jobs._store.get(job_id)
        return job is not None and job.status in {"done", "failed", "cancelled"}
