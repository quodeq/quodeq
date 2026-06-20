"""Run/job index access — wraps JobManager + the SQLite run index.

Owns the read-side query path for evaluations: ``list``, ``get_status``,
``delete``, ``is_complete``, ``get_log_run_dir``, plus the
``promote_stale_to_cancelled`` fallback used by ``cancel_evaluation``.

The ``ActionProvider`` methods on ``FilesystemActionProvider`` are 1-line
delegates to an instance of this class.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from quodeq.core.types.job import JobSnapshot
from quodeq.services import run_index as _run_index
from quodeq.services.jobs import JobManager

_TERMINAL_STATUS_STATES = {"complete", "completed", "done", "cancelled", "failed", "lost"}


def _status_json_terminal(run_dir: Path) -> bool:
    """Return True when the run's status.json says it ended."""
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return False
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    state = data.get("state")
    return isinstance(state, str) and state in _TERMINAL_STATUS_STATES


class EvaluationsIndex:
    """Indexed view of evaluation runs.

    Bridges in-memory ``JobManager`` state and the persistent SQLite index
    so callers see one merged set of runs regardless of provenance.
    """

    def __init__(
        self,
        jobs: JobManager,
        index_db_path: Path | None = None,
        reports_root: Path | None = None,
    ) -> None:
        self._jobs = jobs
        self._index_db_path = Path(index_db_path) if index_db_path is not None else None
        self._reports_root = reports_root

    # -- public API -----------------------------------------------------

    def list(
        self,
        limit: int = 0,
        reports_dir: Path | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
        """Return runs from the SQLite index merged with in-memory jobs."""
        reports_dir = self._coerce_reports_dir(reports_dir)
        db = self._open_index()
        try:
            _run_index.sync_index(db, reports_dir)
            rows = _run_index.list_runs(db, limit=0)  # fetch all, merge, then limit
        finally:
            db.close()
        snapshots = [self._run_row_to_snapshot(r) for r in rows]
        # Internal dashboard-spawned jobs always take priority over index rows
        # that project the same on-disk run. The dedup key is (project, run_id)
        # rather than job_id because internal jobs carry bare UUIDs while
        # indexed rows carry "ext-<run_id>" — keying on job_id never matches
        # the two views of the same run and both end up in the merged list.
        try:
            internal_jobs = self._jobs.list_jobs(reports_root=None)
        except (AttributeError, TypeError):
            internal_jobs = []
        covered = {
            (j.output_project, j.output_run_id) for j in internal_jobs
            if j.output_project and j.output_run_id
        }
        merged = [
            s for s in snapshots
            if (s.output_project, s.output_run_id) not in covered
        ] + list(internal_jobs)
        if states:
            merged = [s for s in merged if s.status in states]
        merged.sort(key=lambda s: s.started_at or "", reverse=True)
        return merged[:limit] if limit and limit > 0 else merged

    def delete(self, job_id: str, reports_dir: Path | None = None) -> bool:
        """Delete a run's on-disk dir and index row. Refuses running jobs."""
        snapshot = self.get_status(job_id, reports_dir=reports_dir)
        if snapshot is None:
            return False
        if snapshot.status == "running":
            return False
        reports_dir = self._coerce_reports_dir(reports_dir)
        # Job IDs of form "ext-<run_uuid>"; run_uuid is also the run directory name.
        run_uuid = job_id[len("ext-"):] if job_id.startswith("ext-") else job_id
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

    def get_status(self, job_id: str, reports_dir: Path | None = None) -> JobSnapshot | None:
        """Return a single run's snapshot.

        Internal job_ids resolve from JobManager (in-memory wins). External
        ``ext-`` ids resolve from the SQLite index after a scoped sync so
        stale runs get promoted to cancelled on this request.
        """
        if not job_id.startswith("ext-"):
            try:
                internal = self._jobs.get_job(job_id, reports_root=None) if hasattr(self._jobs, "get_job") else None
            except TypeError:
                internal = None
            if internal is not None:
                return internal

        reports_dir = self._coerce_reports_dir(reports_dir)
        db = self._open_index()
        try:
            if job_id.startswith("ext-"):
                run_id = job_id[len("ext-"):]
                for project_dir in (reports_dir.iterdir() if reports_dir.is_dir() else []):
                    candidate = project_dir / run_id
                    if candidate.is_dir():
                        _run_index.sync_index_for_run(db, candidate)
                        break
                else:
                    _run_index.sync_index(db, reports_dir)
            else:
                _run_index.sync_index(db, reports_dir)
            row = _run_index.get_run(db, job_id)
        finally:
            db.close()
        if row is None:
            return None
        return self._run_row_to_snapshot(row)

    def promote_stale_to_cancelled(
        self, job_id: str, reports_dir: str | None = None,
    ) -> bool:
        """Force-promote a stuck "running" index row to ``cancelled(stale_detected)``.

        Used as the fallback when ``cancel_evaluation`` finds the underlying
        process is already gone. Returns True if the row was promoted (or
        nothing left to cancel), False if the row is already terminal.
        """
        snapshot = self.get_status(job_id, reports_dir=Path(reports_dir) if reports_dir else None)
        if snapshot is None:
            # Nothing to cancel — the user's intent is satisfied.
            return True
        if snapshot.status != "running":
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

    def get_log_run_dir(self, job_id: str) -> Path | None:
        """Return the run_dir for *job_id*, or None if unknown.

        Accepts either a bare run_id ("d5b8a421-...") or an "ext-<run_id>"
        form. For active jobs we look up output_project/output_run_id via the
        jobs index (efficient); for completed runs without a job entry we fall
        back to a filesystem scan so the SSE endpoint keeps working for any
        run that exists on disk.
        """
        run_id = job_id[len("ext-"):] if job_id.startswith("ext-") else job_id

        # Active-job fast path: trust the jobs index when present.
        if not job_id.startswith("ext-"):
            snapshot = self._jobs.get_job(job_id)
            if (
                snapshot is not None
                and snapshot.output_project is not None
                and snapshot.output_run_id is not None
            ):
                reports_root = self._resolve_reports_root()
                if reports_root is not None:
                    candidate = reports_root / snapshot.output_project / snapshot.output_run_id
                    if candidate.is_dir():
                        return candidate

        # Filesystem fallback: scan reports_root for <project>/<run_id>/.
        reports_root = self._resolve_reports_root()
        if reports_root is None or not reports_root.is_dir():
            return None
        resolved_root = reports_root.resolve()
        for project_dir in reports_root.iterdir():
            if not project_dir.is_dir():
                continue
            candidate = project_dir / run_id
            try:
                if not candidate.resolve().is_relative_to(resolved_root):
                    continue
            except (OSError, ValueError):
                continue
            if candidate.is_dir():
                return candidate
        return None

    def rebuild(self, reports_root: Path | None = None) -> tuple[int, int]:
        """Rebuild the index from scratch by walking *reports_root*.

        Returns ``(rows_written, elapsed_ms)``. Used by the
        ``/api/index/rebuild`` admin endpoint.
        """
        if reports_root is None:
            from quodeq.shared._env import get_evaluations_dir
            reports_root = Path(get_evaluations_dir())
        db = self._open_index()
        try:
            return _run_index.rebuild_index(db, reports_root)
        finally:
            db.close()

    @property
    def index_db_path(self) -> Path | None:
        """The resolved path to the index DB (lazily set on first ``_open_index``)."""
        return self._index_db_path

    def is_complete(self, job_id: str) -> bool:
        """Return True if *job_id* has reached a terminal state."""
        if job_id.startswith("ext-"):
            run_dir = self.get_log_run_dir(job_id)
            if run_dir is None:
                return False
            if (run_dir / "scan.json").exists():
                return True
            if _status_json_terminal(run_dir):
                return True
            from quodeq.services._external_jobs import resolve_external_pid
            pid_file = run_dir / ".pid"
            if not pid_file.exists():
                return True  # no PID file -> stale/crashed -> complete
            project_uuid = run_dir.parent.name
            run_id = run_dir.name
            reports_root = run_dir.parent.parent
            return resolve_external_pid(project_uuid, run_id, reports_root) is None
        snapshot = self._jobs.get_job(job_id)
        if snapshot is not None and snapshot.status in {"done", "failed", "cancelled"}:
            return True
        # Fall back to disk: scan.json or terminal status.json mean the run
        # is over. Covers eviction from the in-memory store and the gap
        # between runner outputs and dashboard's status flip — without this
        # the SSE log-stream would tail forever and never emit `event: done`.
        run_dir = self.get_log_run_dir(job_id)
        if run_dir is None:
            return False
        if (run_dir / "scan.json").exists():
            return True
        return _status_json_terminal(run_dir)

    # -- internals ------------------------------------------------------

    def _resolve_reports_root(self) -> Path | None:
        """Return the active reports directory, falling back to env."""
        if self._reports_root is not None:
            return Path(self._reports_root)
        try:
            from quodeq.shared.utils import get_evaluations_dir
            return Path(get_evaluations_dir())
        except Exception:
            return None

    def _coerce_reports_dir(self, reports_dir: Path | None) -> Path:
        """Resolve *reports_dir* to a Path, falling back to the env var."""
        if reports_dir is not None:
            return Path(reports_dir)
        from quodeq.shared._env import get_evaluations_dir
        return Path(get_evaluations_dir())

    def _open_index(self):
        """Open (lazily) the index DB. Resolved from init kwarg or env."""
        if self._index_db_path is None:
            from quodeq.shared._env import get_index_db_path
            self._index_db_path = Path(get_index_db_path())
        return _run_index.open_index(self._index_db_path)

    def _run_row_to_snapshot(self, row: "_run_index.RunRow") -> JobSnapshot:
        logs: list[str] = []
        dimensions: list[str] | None = None
        deadline_at: str | None = None
        ai_provider: str | None = None
        ai_model: str | None = None
        if row.run_dir:
            run_dir_path = Path(row.run_dir)
            try:
                logs = _tail_run_log(run_dir_path)
            except (OSError, ValueError):
                logs = []
            try:
                dimensions = _read_dimensions_from_status(run_dir_path)
            except (OSError, ValueError):
                dimensions = None
            try:
                deadline_at = _read_deadline_from_status(run_dir_path)
            except (OSError, ValueError):
                deadline_at = None
            try:
                ai_provider, ai_model = _read_provider_model_from_status(run_dir_path)
            except (OSError, ValueError):
                ai_provider, ai_model = None, None
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
            ai_provider=ai_provider,
            ai_model=ai_model,
        )


def _tail_run_log(run_dir: Path, max_lines: int = 500) -> list[str]:
    """Return the last *max_lines* lines from run.log."""
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


def _read_dimensions_from_status(run_dir: Path) -> list[str] | None:
    """Read the `dimensions` list from status.json, or None if unavailable."""
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dims = data.get("dimensions")
    return dims if isinstance(dims, list) else None


def _read_deadline_from_status(run_dir: Path) -> str | None:
    """Read the `deadline_at` ISO string from status.json, or None.

    External (CLI) runs are not tracked by JobManager so they don't go
    through the marker-parsing path that sets ``Job.deadline_at``. Reading
    directly from status.json keeps the dashboard's countdown ticking.
    """
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    val = data.get("deadline_at")
    return val if isinstance(val, str) else None


def _read_provider_model_from_status(run_dir: Path) -> tuple[str | None, str | None]:
    """Read (ai_provider, ai_model) from status.json, or (None, None).

    External (CLI) runs aren't tracked by JobManager, so they don't carry
    provider/model on an in-memory Job. Reading directly from status.json
    keeps the dashboard's in-progress card self-describing for ext- runs.
    """
    status_path = run_dir / "status.json"
    if not status_path.is_file():
        return (None, None)
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (None, None)
    if not isinstance(data, dict):
        return (None, None)
    provider = data.get("ai_provider")
    model = data.get("ai_model")
    return (
        provider if isinstance(provider, str) else None,
        model if isinstance(model, str) else None,
    )
