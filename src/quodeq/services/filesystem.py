"""Filesystem-backed implementation of the ActionProvider interface."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import ProjectEntry, ViolationSummary, to_camel_dict


_TERMINAL_STATUS_STATES = {"complete", "completed", "done", "cancelled", "failed", "lost"}


def _status_json_terminal(run_dir: Path) -> bool:
    """Return True when the run's status.json says it ended."""
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return False
    try:
        data = json.loads(status_path.read_text())
    except (OSError, ValueError):
        return False
    state = data.get("state")
    return isinstance(state, str) and state in _TERMINAL_STATUS_STATES
from quodeq.core.types.job import JobSnapshot
from quodeq.services import _fs_projects, _fs_reports
from quodeq.services import run_index as _run_index
from quodeq.services._ephemeral_cleanup import maybe_cleanup_after_job
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

        # Delete the ephemeral clone (if any) when its evaluation completes.
        # JobManager already wraps callbacks in try/except so exceptions here
        # are logged, never raised back into the job lifecycle.
        def _on_complete(job_id: str, job) -> None:
            project_uuid = job.output_project
            if not project_uuid:
                return
            from quodeq.shared._env import get_clones_dir, get_evaluations_dir
            reports = Path(reports_root) if reports_root is not None else Path(get_evaluations_dir())
            maybe_cleanup_after_job(
                reports_root=reports,
                project_uuid=project_uuid,
                clones_root=get_clones_dir(),
            )
            self._trigger_post_run_projection(job_id, job, reports_root=str(reports))

        # When a JobManager is injected (tests, alternative wiring), the caller
        # is responsible for wiring cleanup callbacks. We do not mutate an
        # externally-owned manager's private state.
        self._jobs = job_manager or JobManager(
            reports_root=reports_root, on_job_complete=_on_complete
        )
        self._compiled_dir = compiled_dir
        self._index_db_path = Path(index_db_path) if index_db_path is not None else None
        self._model_fetchers: dict[str, Callable] = {
            "claude": self._get_claude_models,
        }
        self._project_cache: dict[str, Any] | None = None
        self._project_cache_time: float = 0

    # -- post-run projection --------------------------------------------

    def _trigger_post_run_projection(
        self, job_id: str, job: Any, *, reports_root: str,
    ) -> None:
        """Project events.jsonl → evaluation.db after a run completes.

        Called from the _on_complete callback. No-op when events.jsonl does
        not exist. Logs a warning on failure but never raises.
        """
        project_uuid = getattr(job, "output_project", None)
        run_id = getattr(job, "output_run_id", None)
        if not project_uuid or not run_id:
            return
        run_dir = Path(reports_root) / project_uuid / run_id
        events_log = run_dir / "events.jsonl"
        if not events_log.is_file():
            return
        try:
            from quodeq.data.projection.engine import ProjectionEngine  # noqa: PLC0415
            ProjectionEngine().rebuild(events_log, run_dir)
        except Exception:
            import logging  # noqa: PLC0415
            logging.getLogger(__name__).warning(
                "Post-run projection failed for %s/%s", project_uuid, run_id, exc_info=True,
            )

    # -- index helpers --------------------------------------------------

    def _open_index(self):
        """Open (lazily) the index DB. Resolved from init kwarg or env."""
        if self._index_db_path is None:
            from quodeq.shared._env import get_index_db_path
            self._index_db_path = Path(get_index_db_path())
        return _run_index.open_index(self._index_db_path)

    def list_evaluations(
        self,
        limit: int = 0,
        reports_dir: Path | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
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
        if states:
            merged = [s for s in merged if s.status in states]
        merged.sort(key=lambda s: s.started_at or "", reverse=True)
        return merged[:limit] if limit and limit > 0 else merged

    def delete_evaluation(self, job_id: str, reports_dir: Path | None = None) -> bool:
        """Delete a run's on-disk dir and index row. Refuses to delete a running job."""
        import shutil

        snapshot = self.get_evaluation_status(job_id, reports_dir=reports_dir)
        if snapshot is None:
            return False
        if snapshot.status == "running":
            return False
        if reports_dir is None:
            from quodeq.shared._env import get_evaluations_dir
            reports_dir = Path(get_evaluations_dir())
        else:
            reports_dir = Path(reports_dir)
        # Job IDs of form "ext-<run_uuid>"; run_uuid is also the run directory name.
        run_uuid = job_id[len("ext-"):] if job_id.startswith("ext-") else job_id
        # Scan all project dirs for the run directory (runs are nested by project).
        removed_dir = False
        if reports_dir.is_dir():
            for project_dir in reports_dir.iterdir():
                candidate = project_dir / run_uuid
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
                    removed_dir = True
                    break
        # Remove from index regardless so stale rows get cleaned up.
        db = self._open_index()
        try:
            _run_index.delete_run(db, job_id)
        finally:
            db.close()
        # Also drop any in-memory JobManager entry.
        try:
            if hasattr(self._jobs, "delete"):
                self._jobs.delete(job_id)
        except (KeyError, AttributeError):
            pass
        return removed_dir

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

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running job. Falls back to ``stale_detected`` promotion
        when SIGTERM has nothing to signal (PID dead).

        The base mixin's ``cancel_evaluation`` returns False when the
        underlying process is gone, which the route turns into 409 — leaving
        the user stuck on an "Evaluation in Progress" panel that won't
        progress. After verifying the snapshot was non-terminal, we promote
        the index row to ``cancelled(stale_detected)`` so the UI flips out
        of "running" and the user can close the panel. The row stays in the
        index (history preserved) and findings on disk are not touched.
        """
        ok = super().cancel_evaluation(
            job_id, reports_dir=reports_dir, discard_partial=discard_partial,
        )
        if ok:
            return True

        snapshot = self.get_evaluation_status(job_id, reports_dir=reports_dir)
        if snapshot is None:
            # The row is gone — either it never existed, or the orphan sweep
            # inside ``sync_index`` removed it during ``super()``'s call. The
            # user's intent ("stop this job") is satisfied: there's nothing
            # running. Report success so the UI escapes the stuck panel.
            return True
        if snapshot.status != "running":
            # Already terminal — preserve original contract (don't fabricate
            # a state transition).
            return False

        from quodeq.services._index_sync import force_promote_to_cancelled_stale

        run_dir: Path | None = None
        if snapshot.output_project and snapshot.output_run_id and reports_dir:
            candidate = Path(reports_dir) / snapshot.output_project / snapshot.output_run_id
            if candidate.is_dir():
                run_dir = candidate

        db = self._open_index()
        try:
            with db:
                return force_promote_to_cancelled_stale(db, job_id, run_dir=run_dir)
        finally:
            db.close()

    @staticmethod
    def _tail_run_log(run_dir: Path, max_lines: int = 500) -> list[str]:
        """Return the last *max_lines* lines from run.log. Cheap for normal logs."""
        log_path = run_dir / "run.log"
        if not log_path.is_file():
            return []
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as fp:
                lines = fp.readlines()
        except OSError:
            return []
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return [line.rstrip("\n") for line in tail]

    @staticmethod
    def _read_dimensions_from_status(run_dir: Path) -> list[str] | None:
        """Read the `dimensions` list from status.json, or None if unavailable."""
        import json as _json  # noqa: PLC0415
        status_path = run_dir / "status.json"
        if not status_path.is_file():
            return None
        try:
            data = _json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        dims = data.get("dimensions")
        return dims if isinstance(dims, list) else None

    @staticmethod
    def _read_deadline_from_status(run_dir: Path) -> str | None:
        """Read the `deadline_at` ISO string from status.json, or None if unavailable.

        External (CLI) runs are not tracked by ``JobManager`` and so don't go
        through the marker-parsing path that sets ``Job.deadline_at``. Reading
        directly from status.json — which the run lifecycle writes via
        ``write_status(deadline_at=...)`` — keeps the dashboard's countdown
        timer ticking for external runs too.
        """
        import json as _json  # noqa: PLC0415
        status_path = run_dir / "status.json"
        if not status_path.is_file():
            return None
        try:
            data = _json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        val = data.get("deadline_at")
        return val if isinstance(val, str) else None

    def _run_row_to_snapshot(self, row: "_run_index.RunRow") -> JobSnapshot:
        logs: list[str] = []
        dimensions: list[str] | None = None
        deadline_at: str | None = None
        if row.run_dir:
            run_dir_path = Path(row.run_dir)
            try:
                logs = self._tail_run_log(run_dir_path)
            except (OSError, ValueError):
                logs = []
            try:
                dimensions = self._read_dimensions_from_status(run_dir_path)
            except (OSError, ValueError):
                dimensions = None
            try:
                deadline_at = self._read_deadline_from_status(run_dir_path)
            except (OSError, ValueError):
                deadline_at = None
        return JobSnapshot(
            job_id=row.job_id,
            status=row.state,
            command="",
            started_at=row.started_at,
            ended_at=row.finalized_at,
            exit_code=None,
            logs=logs,
            output_project=row.project_uuid,
            output_run_id=row.run_id,
            phase=row.phase,
            deadline_at=deadline_at,
            current_dimension=row.current_dimension,
            dimensions=dimensions,
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
            if _status_json_terminal(run_dir):
                return True
            # Stale detection: no scan.json AND no live PID -> treat as complete.
            from quodeq.services._external_jobs import resolve_external_pid
            pid_file = run_dir / ".pid"
            if not pid_file.exists():
                return True  # no PID file -> stale/crashed -> complete
            project_uuid = run_dir.parent.name
            run_id = run_dir.name
            reports_root = run_dir.parent.parent
            return resolve_external_pid(project_uuid, run_id, reports_root) is None
        job = self._jobs._store.get(job_id)
        if job is not None and job.status in {"done", "failed", "cancelled"}:
            return True
        # Fall back to disk: scan.json or a terminal status.json mean the
        # run is over. Covers the case where the job was evicted from the
        # in-memory store, or where the runner wrote its outputs but the
        # dashboard's in-memory status flip is still in flight — without
        # this the SSE log-stream would tail forever and never emit
        # `event: done`.
        run_dir = self.get_log_run_dir(job_id)
        if run_dir is None:
            return False
        if (run_dir / "scan.json").exists():
            return True
        return _status_json_terminal(run_dir)
