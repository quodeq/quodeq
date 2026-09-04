"""Run/job index access — wraps JobManager + the SQLite run index.

Owns the read-side query path for evaluations: ``list``, ``get_status``,
``delete``, ``is_complete``, ``get_log_run_dir``, plus the
``promote_stale_to_cancelled`` fallback used by ``cancel_evaluation``. The
``ActionProvider`` methods on ``FilesystemActionProvider`` are 1-line
delegates to an instance of this class.

Split (Task 14, + fix round): status.json readers, the terminal-state check,
and ``RunRow`` -> ``JobSnapshot`` assembly live in ``_run_status_readers.py``
(re-exported — tests import readers directly); directory-removal,
filesystem-fallback-scan, and external-job liveness (none patched by any
test) live in ``_run_index_fs.py`` as plain free functions.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.core.types.job import JobSnapshot
from quodeq.data.sqlite import run_index as _run_index
from quodeq.services._external_jobs import is_safe_run_segment
from quodeq.services.jobs import JobManager
from quodeq.services._run_index_fs import (
    _external_job_is_complete, _merge_internal_jobs, _remove_run_directory, _scan_reports_root_for_run,
)
from quodeq.services._run_status_readers import build_job_snapshot
from quodeq.services._run_status_readers import (  # noqa: F401 — re-export
    _read_deadline_from_status, _read_dimensions_from_status, _read_provider_model_from_status,
    _read_time_limit_from_status, _status_json_terminal, _tail_run_log,
)

_logger = logging.getLogger(__name__)


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
        try:
            internal_jobs = self._jobs.list_jobs(reports_root=None)
        except (AttributeError, TypeError):
            internal_jobs = []
        # limit>0: over-fetch by len(internal_jobs) so that even if every
        # in-memory job dedupes against (and removes) a fetched DB row, the
        # fetch still leaves >= limit usable DB rows to fill the merge.
        # limit<=0 means "fetch all" — leave that path untouched.
        db_limit = limit + len(internal_jobs) if limit and limit > 0 else 0
        db = self._open_index()
        try:
            _run_index.sync_index(db, reports_dir)
            rows = _run_index.list_runs(db, limit=db_limit)
        finally:
            db.close()
        snapshots = [self._run_row_to_snapshot(r) for r in rows]
        merged = _merge_internal_jobs(snapshots, internal_jobs)
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
        # External job IDs are "ext-<run_uuid>" where run_uuid is also the
        # run directory name. Internal job IDs are unrelated to the directory
        # name, so prefer the snapshot's own run coordinates when present.
        run_uuid = job_id[len("ext-"):] if job_id.startswith("ext-") else job_id
        if snapshot.output_run_id:
            run_uuid = snapshot.output_run_id
        removed_dir = _remove_run_directory(
            reports_dir, snapshot.output_project, run_uuid, log=_logger,
        )
        # Remove from index regardless so stale rows get cleaned up. The same
        # on-disk run can be indexed under "ext-<run_uuid>" even when the
        # caller holds the internal job id, so clear both key forms.
        db = self._open_index()
        try:
            _run_index.delete_run(db, job_id)
            if run_uuid != job_id:
                _run_index.delete_run(db, f"ext-{run_uuid}")
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
                if not is_safe_run_segment(run_id):
                    return None
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

        from quodeq.data.sqlite._index_sync import force_promote_to_cancelled_stale

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
        return _scan_reports_root_for_run(self._resolve_reports_root(), run_id)

    def rebuild(self, reports_root: Path | None = None) -> tuple[int, int]:
        """Rebuild the index from scratch by walking *reports_root*.

        Returns ``(rows_written, elapsed_ms)``. Used by the
        ``/api/index/rebuild`` admin endpoint.
        """
        root = reports_root if reports_root is not None else self._reports_root
        db = self._open_index()
        try:
            return _run_index.rebuild_index(db, root)
        finally:
            db.close()

    @property
    def index_db_path(self) -> Path | None:
        """The path to the index DB, injected at construction."""
        return self._index_db_path

    def is_complete(self, job_id: str) -> bool:
        """Return True if *job_id* has reached a terminal state."""
        if job_id.startswith("ext-"):
            run_dir = self.get_log_run_dir(job_id)
            if run_dir is None:
                return False
            return _external_job_is_complete(run_dir)
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
        """Return the active reports directory (injected at construction)."""
        return Path(self._reports_root) if self._reports_root is not None else None

    def _coerce_reports_dir(self, reports_dir: Path | None) -> Path:
        """Resolve *reports_dir* to a Path, falling back to the injected reports_root."""
        if reports_dir is not None:
            return Path(reports_dir)
        return Path(self._reports_root)

    def _open_index(self):
        """Open the index DB at the injected path."""
        if self._index_db_path is None:
            raise ValueError("EvaluationsIndex requires index_db_path to be set")
        return _run_index.open_index(self._index_db_path)

    def _run_row_to_snapshot(self, row: "_run_index.RunRow") -> JobSnapshot:
        return build_job_snapshot(row)
