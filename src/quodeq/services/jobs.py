"""Background job management for evaluation subprocesses."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any, Callable, Iterable

import logging
import subprocess

from quodeq.core.types import JobSnapshot

from quodeq.analysis._process import _kill_tree
from quodeq.services._job_model import (
    Job,
    JobStore,
    InMemoryJobStore,
    FileJobStore,
    create_job_store,
    REPORT_PATH_RE,
    _MAX_COMPLETED_JOBS,
    _ANSI_RE,
    _CC_MARKER_PREFIX,
    _CONSUME_BATCH_SIZE,
)

# Re-export public names so existing imports from this module keep working.
__all__ = [
    "Job",
    "JobStore",
    "InMemoryJobStore",
    "FileJobStore",
    "create_job_store",
    "REPORT_PATH_RE",
    "JobManager",
]

# NOTE: logging in inner layer — tracked for middleware extraction
_logger = logging.getLogger(__name__)
_REPORT_PATH_MARKER = "Report path:"
_PROCESS_WAIT_TIMEOUT_S = 30
_EXIT_CODE_SPAWN_FAILURE = -1
_EXIT_CODE_TIMEOUT = -9
_DEFAULT_LIST_LIMIT = 100

# Canonical job status strings.
STATUS_RUNNING = "running"
STATUS_CANCELLED = "cancelled"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class JobManager:
    """Thread-safe manager for spawning and tracking evaluation subprocesses.

    NOTE: Job state is stored via a ``JobStore`` (defaulting to in-memory).
    To support horizontal scaling, supply a persistent ``JobStore``
    implementation (e.g. database, Redis) to the constructor.
    """

    def __init__(
        self,
        spawn_impl: Callable[..., subprocess.Popen] | None = None,
        job_store: JobStore | None = None,
        on_job_complete: Callable[[str, Job], None] | None = None,
    ) -> None:
        self._spawn = spawn_impl or subprocess.Popen
        self._store: JobStore = job_store or create_job_store()
        self._processes: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._on_job_complete = on_job_complete

    def start_job(self, cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> JobSnapshot:
        """Spawn a subprocess and return its initial job state."""
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            status=STATUS_RUNNING,
            command=cmd,
            started_at=datetime.now(timezone.utc).isoformat(),
            ended_at=None,
            exit_code=None,
        )

        try:
            process = self._spawn(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _logger.error("Failed to start job subprocess: %s", exc)
            job.status = STATUS_FAILED
            job.ended_at = datetime.now(timezone.utc).isoformat()
            job.exit_code = _EXIT_CODE_SPAWN_FAILURE
            job.logs.append(f"Failed to start process: {exc}")
            with self._lock:
                self._store.put(job)
            result = job.to_dict()
            return replace(result, error=str(exc))

        with self._lock:
            self._store.put(job)
            self._processes[job_id] = process

        threading.Thread(target=self._consume_stream, args=(job_id, process.stdout), daemon=True).start()
        threading.Thread(target=self._monitor_process, args=(job_id, process), daemon=True).start()

        return job.to_dict()

    def cancel_job(self, job_id: str, reports_root: Path | None = None) -> bool:
        """Terminate a running job. Return True if cancelled successfully.

        For external jobs (``ext-`` prefix), sends SIGTERM to the process that
        owns the run.  For internal jobs, kills the tracked subprocess.
        """
        if job_id.startswith("ext-") and reports_root is not None:
            return self._cancel_external(job_id, reports_root)
        return self._cancel_internal(job_id)

    def _cancel_internal(self, job_id: str) -> bool:
        """Kill an internal tracked subprocess."""
        with self._lock:
            job = self._store.get(job_id)
            process = self._processes.get(job_id)
            if not job or job.status != STATUS_RUNNING:
                return False
            job.status = STATUS_CANCELLED
            job.ended_at = datetime.now(timezone.utc).isoformat()
            self._store.put(job)
        if process:
            _kill_tree(process.pid)
        return True

    def _cancel_external(self, job_id: str, reports_root: Path) -> bool:
        """Send SIGTERM to an external run's process."""
        from quodeq.services._external_jobs import cancel_external_run
        run_id = job_id[len("ext-"):]
        for project_dir in reports_root.iterdir():
            if not project_dir.is_dir():
                continue
            if (project_dir / run_id).is_dir():
                return cancel_external_run(project_dir.name, run_id, reports_root)
        return False

    def shutdown(self) -> None:
        """Kill all running job subprocesses. Called on server shutdown."""
        with self._lock:
            for job_id, process in list(self._processes.items()):
                try:
                    _kill_tree(process.pid)
                except (ProcessLookupError, OSError):
                    pass
            self._processes.clear()

    def get_job(self, job_id: str, reports_root: Path | None = None) -> JobSnapshot | None:
        """Return the current state of a job, or None if not found.

        For external jobs (``ext-`` prefix), reconstructs the snapshot from
        the filesystem instead of the in-process store.
        """
        if job_id.startswith("ext-") and reports_root is not None:
            return self._get_external(job_id, reports_root)
        with self._lock:
            job = self._store.get(job_id)
            if not job:
                return None
            return job.to_dict()

    def _get_external(self, job_id: str, reports_root: Path) -> JobSnapshot | None:
        """Reconstruct a JobSnapshot for an external run from its run directory."""
        from quodeq.services._external_jobs import _run_dir_to_snapshot
        run_id = job_id[len("ext-"):]
        for project_dir in reports_root.iterdir():
            if not project_dir.is_dir():
                continue
            run_dir = project_dir / run_id
            if run_dir.is_dir():
                return _run_dir_to_snapshot(project_dir.name, run_dir)
        return None

    def list_jobs(
        self,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
        reports_root: Path | None = None,
    ) -> list[JobSnapshot]:
        """Return tracked jobs as frozen snapshots with pagination.

        When *reports_root* is provided, external in-progress runs are merged
        in.  Internal jobs take priority: if both share the same
        (output_project, output_run_id), the internal entry wins.

        When *limit* is 0 all jobs are returned (no cap).
        """
        with self._lock:
            internal = [job.to_dict() for job in self._store.list()]

        merged: list[JobSnapshot] = list(internal)

        if reports_root is not None and reports_root.is_dir():
            from quodeq.services._external_jobs import find_external_runs
            externals = find_external_runs(reports_root)
            internal_keys = {
                (j.output_project, j.output_run_id)
                for j in internal
                if j.output_project and j.output_run_id
            }
            for ext in externals:
                key = (ext.output_project, ext.output_run_id)
                if key not in internal_keys:
                    merged.append(ext)

        # Sort newest-first, then paginate
        merged.sort(key=lambda j: j.started_at or "", reverse=True)
        page = merged[offset:] if offset else merged
        return page[:limit] if limit > 0 else page

    @staticmethod
    def _apply_marker(job: Job, line: str) -> None:
        """Parse a structured JSON marker and update job state."""
        try:
            marker = json.loads(line)
        except json.JSONDecodeError:
            return
        phase = marker.get("_cc")
        if phase == "setup":
            job.phase = "setup"
            job.dimensions = marker.get("dimensions")
        elif phase in ("analyzing", "scoring"):
            job.current_dimension = marker.get("dimension")
            job.phase = phase
        elif phase == "report_path":
            project = marker.get("project")
            run_id = marker.get("runId")
            if project and run_id:
                job.output_project = project
                job.output_run_id = run_id

    def _append_log(self, job: Job, line: str) -> None:
        if not line:
            return
        if line.startswith(_CC_MARKER_PREFIX):
            self._apply_marker(job, line)
            return
        job.logs.append(_ANSI_RE.sub("", line))
        # Fallback: extract report path from log text if the structured
        # marker was not received (backward compat with older pipelines).
        if not job.output_project and _REPORT_PATH_MARKER in line:
            match = REPORT_PATH_RE.search(line)
            if match:
                job.output_project = match.group(1)
                job.output_run_id = match.group(2)

    def _flush_batch(self, job_id: str, batch: list[str]) -> bool:
        """Write accumulated log lines to the job. Returns False if job disappeared."""
        with self._lock:
            job = self._store.get(job_id)
            if not job:
                return False
            for stripped in batch:
                self._append_log(job, stripped)
        return True

    def _consume_stream(self, job_id: str, stream: Iterable[str] | None) -> None:
        if stream is None:
            return
        batch: list[str] = []
        try:
            for line in stream:
                batch.append(line.rstrip("\n"))
                if len(batch) >= _CONSUME_BATCH_SIZE:
                    if not self._flush_batch(job_id, batch):
                        return
                    batch.clear()
        except (IOError, BrokenPipeError) as exc:
            _logger.warning("Stream read error for job %s: %s", job_id, exc)
        if batch:
            self._flush_batch(job_id, batch)

    def _evict_completed_jobs(self) -> None:
        """Remove oldest completed/failed/cancelled jobs beyond _MAX_COMPLETED_JOBS."""
        all_jobs = self._store.list()
        completed = [j.job_id for j in all_jobs if j.status != STATUS_RUNNING]
        excess = len(completed) - _MAX_COMPLETED_JOBS
        if excess > 0:
            for jid in completed[:excess]:
                self._store.delete(jid)

    @property
    def _job_timeout_s(self) -> int:
        """Job timeout in seconds — reads from env at call time for lazy configuration."""
        return int(os.environ.get("QUODEQ_JOB_TIMEOUT_S", "7200"))

    def _monitor_process(self, job_id: str, process: subprocess.Popen) -> None:
        try:
            exit_code = process.wait(timeout=self._job_timeout_s)
        except subprocess.TimeoutExpired:
            _logger.warning("Job %s exceeded %ds timeout — killing", job_id, self._job_timeout_s)
            process.kill()
            process.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
            exit_code = _EXIT_CODE_TIMEOUT
        with self._lock:
            self._processes.pop(job_id, None)
            job = self._store.get(job_id)
            if not job or job.status == STATUS_CANCELLED:
                return
            job.exit_code = exit_code
            job.ended_at = datetime.now(timezone.utc).isoformat()
            job.status = STATUS_DONE if exit_code == 0 else STATUS_FAILED
            self._store.put(job)
            self._evict_completed_jobs()
        if self._on_job_complete is not None:
            try:
                self._on_job_complete(job_id, job)
            except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
                _logger.error("on_job_complete callback failed for %s: %s", job_id, exc)
