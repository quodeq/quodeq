"""Background job management for evaluation subprocesses."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import threading
import uuid
from typing import TYPE_CHECKING, Any, Callable

import subprocess

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types import JobSnapshot

from quodeq.shared._process_kill import kill_tree as _kill_tree, terminate_process as _terminate_process
from quodeq.shared.run_log import RunLogWriter
from quodeq.services._job_model import (
    Job,
    JobStore,
    InMemoryJobStore,
    REPORT_PATH_RE,
    _MAX_COMPLETED_JOBS,  # noqa: F401 — re-export (patch/import target)
)
from quodeq.services._job_file_store import (
    FileJobStore,
    create_job_store,
)

if TYPE_CHECKING:
    from quodeq.services._external_jobs import ProcessControl

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

_REPORT_PATH_MARKER = "Report path:"
_EXIT_CODE_SPAWN_FAILURE = -1
_EXIT_CODE_TIMEOUT = -9
_DEFAULT_LIST_LIMIT = 100

# Watchdog polls process state every N seconds and re-checks deadline_at,
# which only lands in job state after the analyzing_start marker — so a
# blocking wait(timeout=full_budget) at spawn time can't see it.
_WATCHDOG_POLL_INTERVAL_S = 1.0
# Grace window past deadline_at before the kill. The watchdog exists to
# reap HUNG runs, never to cut loaded agents: past the deadline the pool
# stops dispatching and in-flight model calls drain. The longest
# legitimate in-flight call is one scaled local read timeout (500s per
# subagent, realistically up to 3), so the grace must exceed that or a
# healthy drain gets SIGTERMed and the batch's work is lost.
_WATCHDOG_DEADLINE_GRACE_S = 1800

# Canonical job status strings.
STATUS_RUNNING = "running"
STATUS_CANCELLED = "cancelled"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

# status.json exit reasons that mean "the run hit its time budget" — the
# user's own setting doing its job, not an error. Jobs ending this way are
# marked cancelled (already in the salvage-scoring trigger list in
# api/_evaluation_routes.py) with exit_reason set, so the evaluate header
# renders "time limit reached" instead of FAILED.
_DEADLINE_EXIT_REASONS = ("deadline", "time_limit")
_EXIT_REASON_DEADLINE = "deadline"

# Log/marker parsing and background process monitoring: split into
# _job_monitor_mixin.py to keep this file under 300 lines. Imported here
# (after the constants above, before the class) so that module's
# `from quodeq.services.jobs import ...` resolves against this
# already-initialized part of this (still-loading) module.
from quodeq.services._job_monitor_mixin import _JobMonitorMixin  # noqa: E402


class JobManager(_JobMonitorMixin):
    """Thread-safe manager for spawning and tracking evaluation subprocesses.

    NOTE: Job state is stored via a ``JobStore`` (defaulting to in-memory).
    To support horizontal scaling, supply a persistent ``JobStore``
    implementation (e.g. database, Redis) to the constructor.

    Log/marker parsing and background process monitoring
    (``_apply_marker``, ``_append_log``, ``_flush_batch``,
    ``_consume_stream``, ``_drain_pre_marker_buffer``, ``_tee_run_log``,
    ``_evict_completed_jobs``, ``_job_timeout_cap_s``,
    ``_watchdog_should_kill``, ``_run_status_exit_reason``,
    ``_classify_exit``, ``_monitor_process``) live in ``_JobMonitorMixin``
    (see ``_job_monitor_mixin.py``).
    """

    def __init__(
        self,
        spawn_impl: Callable[..., subprocess.Popen] | None = None,
        job_store: JobStore | None = None,
        on_job_complete: Callable[[str, Job], None] | None = None,
        reports_root: Path | None = None,
        job_timeout_cap_s: float | None = None,
        *, log: LogSink = NULL_LOG,
        process_control: "ProcessControl | None" = None,
    ) -> None:
        self._spawn = spawn_impl or subprocess.Popen
        self._store: JobStore = job_store or create_job_store()
        self._processes: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._on_job_complete = on_job_complete
        self._reports_root: Path | None = reports_root
        self._log = log
        self._process_control = process_control
        # Injection seam for the hard job-duration cap; None means "fall back
        # to the QUODEQ_JOB_TIMEOUT_S env var" (see _job_timeout_cap_s below).
        self._job_timeout_cap_s_override = job_timeout_cap_s
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

    def start_job(self, cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None, ai_provider: str | None = None, ai_model: str | None = None, time_limit_s: int | None = None) -> JobSnapshot:
        """Spawn a subprocess and return its initial job state."""
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            status=STATUS_RUNNING,
            command=cmd,
            started_at=datetime.now(timezone.utc).isoformat(),
            ended_at=None,
            exit_code=None,
            ai_provider=ai_provider,
            ai_model=ai_model,
            time_limit_s=time_limit_s,
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
            self._log.error(f"Failed to start job subprocess: {exc}")
            job.status = STATUS_FAILED
            job.ended_at = datetime.now(timezone.utc).isoformat()
            job.exit_code = _EXIT_CODE_SPAWN_FAILURE
            job.logs.append(f"Failed to start process: {exc}")
            with self._lock:
                self._store.put(job)
            result = job.to_dict()
            return replace(result, error="Failed to start the evaluation process. Check the server logs for details.")

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
        """Kill an internal tracked subprocess, escalating SIGTERM -> SIGKILL.

        Bare SIGTERM doesn't reliably interrupt a child blocked in a long
        httpx socket read (e.g. waiting on an Ollama inference that takes
        minutes) -- the signal queues behind the syscall and the process
        keeps holding the upstream connection. ``_terminate_process`` runs
        SIGTERM with a grace window then escalates to SIGKILL, matching the
        external-cancel path in ``_external_jobs.cancel_external_run``.
        """
        with self._lock:
            job = self._store.get(job_id)
            process = self._processes.get(job_id)
            if not job or job.status != STATUS_RUNNING:
                return False
            job.status = STATUS_CANCELLED
            job.ended_at = datetime.now(timezone.utc).isoformat()
            self._store.put(job)
        if process:
            _terminate_process(process)
        return True

    def _cancel_external(self, job_id: str, reports_root: Path) -> bool:
        """Send SIGTERM to an external run's process."""
        from quodeq.services._external_jobs import cancel_external_run, is_safe_run_segment
        run_id = job_id[len("ext-"):]
        if not is_safe_run_segment(run_id):
            return False
        for project_dir in reports_root.iterdir():
            if not project_dir.is_dir():
                continue
            if (project_dir / run_id).is_dir():
                return cancel_external_run(
                    project_dir.name, run_id, reports_root, control=self._process_control,
                )
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
        """Return the current state of an in-memory job, or None if not found.

        External runs (``ext-`` prefix) are not tracked in-memory — they are
        served by ``FilesystemActionProvider.get_evaluation_status`` via the
        SQLite index. Callers that encounter an ``ext-`` id here should route
        through the provider instead.
        """
        if job_id.startswith("ext-"):
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
            if not job or job.status == STATUS_RUNNING:
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

