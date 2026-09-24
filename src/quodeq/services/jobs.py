"""Background job management for evaluation subprocesses."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import threading
import uuid
from typing import Any, Callable

import subprocess

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.run.exit_reason import DEADLINE_EXIT_REASONS
from quodeq.core.run.job_status import JobStatus, is_external_job_id, strip_external_prefix
from quodeq.core.types import JobSnapshot

from quodeq.shared.process_kill import kill_tree as _kill_tree, terminate_process
from quodeq.shared.run_log import RunLogWriter
from quodeq.services._job_model import (
    Job,
    JobLaunchOptions,
    JobProcessSeams,
    JobStore,
    InMemoryJobStore,
    REPORT_PATH_RE,
    EXIT_CODE_TIMEOUT,
    MAX_COMPLETED_JOBS,
    WATCHDOG_POLL_INTERVAL_S,
    mark_spawn_failed,
    new_job,
)
from quodeq.services._job_monitor_mixin import JobMonitorMixin
from quodeq.services._job_file_store import (
    FileJobStore,
    create_job_store,
)
from quodeq.services._job_capacity_mixin import JobCapacityMixin

# Re-export public names so existing imports from this module keep working.
__all__ = [
    "Job", "JobLaunchOptions", "JobProcessSeams", "JobStore", "InMemoryJobStore",
    "FileJobStore", "create_job_store", "REPORT_PATH_RE", "JobManager", "JobStatus",
    "DEADLINE_EXIT_REASONS",
    # Owned by _job_model (which _job_monitor_mixin also reads them from) and
    # re-exported here: tests import and patch them at this module's path.
    "EXIT_CODE_TIMEOUT", "MAX_COMPLETED_JOBS",
    "WATCHDOG_POLL_INTERVAL_S",
]

_EXIT_CODE_SPAWN_FAILURE = -1
_DEFAULT_LIST_LIMIT = 100

# Grace window past deadline_at before the kill. The watchdog exists to
# reap HUNG runs, never to cut loaded agents: past the deadline the pool
# stops dispatching and in-flight model calls drain. The longest
# legitimate in-flight call is one scaled local read timeout (500s per
# subagent, realistically up to 3), so the grace must exceed that or a
# healthy drain gets SIGTERMed and the batch's work is lost.
WATCHDOG_DEADLINE_GRACE_S = 1800


class JobManager(JobMonitorMixin, JobCapacityMixin):
    """Thread-safe manager for spawning and tracking evaluation subprocesses.

    NOTE: Job state is stored via a ``JobStore`` (defaulting to in-memory).
    To support horizontal scaling, supply a persistent ``JobStore``
    implementation (e.g. database, Redis) to the constructor.

    Log/marker parsing and background process monitoring
    (``_apply_marker``, ``_append_log``, ``_flush_batch``,
    ``_consume_stream``, ``_drain_pre_marker_buffer``, ``_tee_run_log``,
    ``_evict_completed_jobs``, ``_job_timeout_cap_s``,
    ``_watchdog_should_kill``, ``_run_status_exit_reason``,
    ``_classify_exit``, ``_monitor_process``) live in ``JobMonitorMixin``
    (see ``_job_monitor_mixin.py``).
    """

    def __init__(
        self,
        seams: JobProcessSeams | None = None,
        job_store: JobStore | None = None,
        on_job_complete: Callable[[str, Job], None] | None = None,
        reports_root: Path | None = None,
        *, log: LogSink = NULL_LOG,
    ) -> None:
        seams = seams if seams is not None else JobProcessSeams()
        self._spawn = seams.spawn_impl or subprocess.Popen
        self._store: JobStore = job_store or create_job_store()
        self._processes: dict[str, Any] = {}
        # Job ids past the capacity check but not yet spawned, counted
        # against the cap; never in _processes, which cancel/shutdown read.
        self._reserved: set[str] = set()
        self._lock = threading.Lock()
        self._on_job_complete = on_job_complete
        self._reports_root: Path | None = reports_root
        self._log = log
        self._process_control = seams.process_control
        # Injection seam for the hard job-duration cap; None means "fall back
        # to the QUODEQ_JOB_TIMEOUT_S env var" (see _job_timeout_cap_s below).
        self._job_timeout_cap_s_override = seams.job_timeout_cap_s
        # Injection seam for the concurrency cap; None means "fall back to
        # the QUODEQ_MAX_CONCURRENT_JOBS env var" (see _max_concurrent_jobs
        # in _job_capacity_mixin.py).
        self._max_concurrent_jobs_override = seams.max_concurrent_jobs
        # _run_log_writers and _pre_marker_buffer are owned exclusively by the
        # per-job _consume_stream thread started in start_job(). No other code
        # path may read or mutate these dicts — doing so reintroduces the
        # use-after-close race that self._lock does not protect against.
        self._run_log_writers: dict[str, RunLogWriter] = {}
        self._pre_marker_buffer: dict[str, list[str]] = {}

    def set_reports_root(self, path: Path) -> None:
        """Update the reports root used to resolve run.log directories.

        Called by ``FilesystemActionProvider.start_evaluation`` to keep
        ``_reports_root`` consistent with the per-request reports directory.
        """
        self._reports_root = path

    def start_job(self, cmd: list[str], launch: JobLaunchOptions | None = None) -> JobSnapshot:
        """Spawn a subprocess and return its initial job state."""
        launch = launch if launch is not None else JobLaunchOptions()
        job = new_job(str(uuid.uuid4()), cmd, launch, status=JobStatus.RUNNING)
        refusal = self._reserve_slot_or_refuse(job)
        if refusal is not None:
            return refusal

        try:
            process = self._spawn(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=launch.cwd,
                env=launch.env,
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return self._record_spawn_failure(job, exc)

        with self._lock:
            self._store.put(job)
            # The reservation becomes the tracked process under one lock hold,
            # so the slot is never double-counted and never briefly free.
            self._reserved.discard(job.job_id)
            self._processes[job.job_id] = process
        self._start_watchers(job.job_id, process)
        return job.to_dict()

    def _record_spawn_failure(self, job: Job, exc: BaseException) -> JobSnapshot:
        """Persist *job* as failed to start and return the snapshot the caller reports."""
        self._log.error(f"Failed to start job subprocess: {exc}")
        self._release_slot(job.job_id)
        mark_spawn_failed(job, exc, status=JobStatus.FAILED, exit_code=_EXIT_CODE_SPAWN_FAILURE)
        with self._lock:
            self._store.put(job)
        result = job.to_dict()
        return replace(result, error="Failed to start the evaluation process. Check the server logs for details.")

    def _start_watchers(self, job_id: str, process: subprocess.Popen) -> None:
        """Start the per-job stream consumer and exit monitor threads."""
        threading.Thread(target=self._consume_stream, args=(job_id, process.stdout), daemon=True).start()
        threading.Thread(target=self._monitor_process, args=(job_id, process), daemon=True).start()

    def cancel_job(self, job_id: str, reports_root: Path | None = None, run_dir: Path | None = None) -> bool:
        """Terminate a running job. Return True if cancelled successfully.

        For external jobs (``ext-`` prefix), sends SIGTERM to the process that
        owns the run. For internal jobs, kills the tracked subprocess. *run_dir*
        lets ``_cancel_external`` skip its project-directory scan.
        """
        if is_external_job_id(job_id) and reports_root is not None:
            return self._cancel_external(job_id, reports_root, run_dir=run_dir)
        return self._cancel_internal(job_id)

    def _cancel_internal(self, job_id: str) -> bool:
        """Kill an internal tracked subprocess, escalating SIGTERM -> SIGKILL.

        Bare SIGTERM doesn't reliably interrupt a child blocked in a long
        httpx socket read (e.g. waiting on an Ollama inference that takes
        minutes) -- the signal queues behind the syscall and the process
        keeps holding the upstream connection. ``terminate_process`` runs
        SIGTERM with a grace window then escalates to SIGKILL, matching the
        external-cancel path in ``_external_jobs.cancel_external_run``.
        """
        with self._lock:
            job = self._store.get(job_id)
            process = self._processes.get(job_id)
            if not job or job.status != JobStatus.RUNNING:
                return False
            job.status = JobStatus.CANCELLED
            job.ended_at = datetime.now(timezone.utc).isoformat()
            self._store.put(job)
        if process:
            terminate_process(process)
        return True

    def _cancel_external(self, job_id: str, reports_root: Path, run_dir: Path | None = None) -> bool:
        """Send SIGTERM to an external run's process; *run_dir* skips the scan when valid."""
        from quodeq.services._external_jobs import cancel_external_run, is_safe_run_segment, resolve_external_run_project
        run_id = strip_external_prefix(job_id)
        if not is_safe_run_segment(run_id):
            return False
        project_uuid = resolve_external_run_project(reports_root, run_id, run_dir_hint=run_dir)
        if project_uuid is None:
            return False
        return cancel_external_run(project_uuid, run_id, reports_root, control=self._process_control)

    def shutdown(self) -> None:
        """Kill all running job subprocesses. Called on server shutdown."""
        with self._lock:
            for job_id, process in list(self._processes.items()):
                try:
                    _kill_tree(process.pid)
                except (ProcessLookupError, OSError) as exc:
                    self._log.debug(f"job {job_id} process already gone during shutdown: {exc}")
            self._processes.clear()

    def get_job(self, job_id: str) -> JobSnapshot | None:
        """Return the current state of an in-memory job, or None if not found.

        External runs (``ext-`` prefix) are not tracked in-memory — they are
        served by ``FilesystemActionProvider.get_evaluation_status`` via the
        SQLite index. Callers that encounter an ``ext-`` id here should route
        through the provider instead.
        """
        if is_external_job_id(job_id):
            return None
        with self._lock:
            job = self._store.get(job_id)
            if not job:
                return None
            return job.to_dict()

    def delete(self, job_id: str) -> bool:
        """Drop a terminal job from the store. Refuses running jobs.

        Called by ``EvaluationsIndex.delete`` after a discard-cancel removes
        the run dir and index row, so the job stops resurfacing in
        ``/api/evaluations`` from the persisted job store.
        """
        with self._lock:
            job = self._store.get(job_id)
            if not job or job.status == JobStatus.RUNNING:
                return False
            self._store.delete(job_id)
            return True

    def list_jobs(
        self,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
        offset: int = 0,
        reports_root: Path | None = None,
    ) -> list[JobSnapshot]:
        """Return tracked in-memory jobs as frozen snapshots with pagination.

        External runs are served via the SQLite index, not JobManager. The
        ``reports_root`` kwarg is retained for signature compatibility with
        callers that still pass it; it is deprecated and ignored.
        """
        if reports_root is not None:
            import warnings
            warnings.warn(
                "JobManager.list_jobs(reports_root=...) is deprecated and ignored. "
                "External runs are now served via FilesystemActionProvider + the "
                "SQLite index; pass reports_root=None (or omit the kwarg).",
                DeprecationWarning,
                stacklevel=2,
            )
        with self._lock:
            internal = [job.to_dict() for job in self._store.list()]
        # Preserve existing ordering (newest first).
        internal.sort(key=lambda s: s.started_at or "", reverse=True)
        if limit == 0:
            return internal[offset:]
        return internal[offset:offset + limit]

