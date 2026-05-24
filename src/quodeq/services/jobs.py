"""Background job management for evaluation subprocesses."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Callable, Iterable

import logging
import subprocess

from quodeq.core.types import JobSnapshot

from quodeq.analysis._process import _kill_tree, _terminate_process
from quodeq.shared.run_log import RunLogWriter
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

# Watchdog polls process state every N seconds and re-checks deadline_at,
# which only lands in job state after the analyzing_start marker — so a
# blocking wait(timeout=full_budget) at spawn time can't see it.
_WATCHDOG_POLL_INTERVAL_S = 1.0
# Grace window past deadline_at before SIGKILL — gives the analysis side's
# graceful-cancel path time to score completed dimensions.
_WATCHDOG_DEADLINE_GRACE_S = 60

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
        reports_root: Path | None = None,
    ) -> None:
        self._spawn = spawn_impl or subprocess.Popen
        self._store: JobStore = job_store or create_job_store()
        self._processes: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._on_job_complete = on_job_complete
        self._reports_root: Path | None = reports_root
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
        elif phase == "analyzing_start":
            job.deadline_at = marker.get("deadline_at")
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
        self._pre_marker_buffer.setdefault(job_id, [])
        try:
            try:
                for line in stream:
                    stripped = line.rstrip("\n")
                    batch.append(stripped)
                    if len(batch) >= _CONSUME_BATCH_SIZE:
                        if not self._flush_batch(job_id, batch):
                            return
                        batch.clear()
                    # Tee after flush so the marker is already applied to the
                    # job before we try to resolve run_dir. Skip _cc JSON
                    # markers — they are structured IPC, not user-facing
                    # terminal output, and leaking them makes the xterm pane
                    # in the dashboard noisy.
                    if not stripped.startswith(_CC_MARKER_PREFIX):
                        self._tee_run_log(job_id, stripped)
            except (IOError, BrokenPipeError) as exc:
                _logger.warning("Stream read error for job %s: %s", job_id, exc)
            if batch:
                self._flush_batch(job_id, batch)
            # Final drain: if the report_path marker arrived in the last batch,
            # the writer may not have been created yet — try one more time so
            # buffered pre-marker lines are not lost.
            self._drain_pre_marker_buffer(job_id)
        finally:
            # Always release the writer and buffer, even on unexpected exceptions.
            writer = self._run_log_writers.pop(job_id, None)
            if writer is not None:
                writer.close()
            self._pre_marker_buffer.pop(job_id, None)

    def _drain_pre_marker_buffer(self, job_id: str) -> None:
        """Attempt to resolve run_dir and flush any buffered pre-marker lines.

        Called after the final ``_flush_batch`` so that lines buffered before
        the report_path marker are not lost when the marker arrives in the last
        batch of the stream.
        """
        if self._run_log_writers.get(job_id) is not None:
            # Writer already open — nothing to drain.
            return
        job = self._store.get(job_id)
        if job and job.output_project and job.output_run_id and self._reports_root is not None:
            run_dir = self._reports_root / job.output_project / job.output_run_id
            if run_dir.is_dir():
                writer = RunLogWriter(run_dir)
                self._run_log_writers[job_id] = writer
                for pending in self._pre_marker_buffer.get(job_id, []):
                    writer.write(pending)
                self._pre_marker_buffer[job_id] = []

    def _tee_run_log(self, job_id: str, line: str) -> None:
        """Forward *line* to the job's run.log writer.

        Before the report_path marker arrives, ``run_dir`` is unknown — lines
        are held in ``self._pre_marker_buffer`` and flushed once the marker
        resolves the directory.

        Caller invariant: at most one ``_consume_stream`` runs per job_id at a
        time.  This method is not re-entrant for the same job_id.
        """
        writer = self._run_log_writers.get(job_id)
        if writer is None:
            # Try to resolve run_dir from the job snapshot now.
            job = self._store.get(job_id)
            if job and job.output_project and job.output_run_id and self._reports_root is not None:
                run_dir = self._reports_root / job.output_project / job.output_run_id
                if run_dir.is_dir():
                    writer = RunLogWriter(run_dir)
                    self._run_log_writers[job_id] = writer
                    # Flush any buffered pre-marker lines.
                    for pending in self._pre_marker_buffer.get(job_id, []):
                        writer.write(pending)
                    self._pre_marker_buffer[job_id] = []
            if writer is None:
                self._pre_marker_buffer.setdefault(job_id, []).append(line)
                return
        writer.write(line)

    def _evict_completed_jobs(self) -> None:
        """Remove oldest completed/failed/cancelled jobs beyond _MAX_COMPLETED_JOBS."""
        all_jobs = self._store.list()
        completed = [j.job_id for j in all_jobs if j.status != STATUS_RUNNING]
        excess = len(completed) - _MAX_COMPLETED_JOBS
        if excess > 0:
            for jid in completed[:excess]:
                self._store.delete(jid)

    @property
    def _job_timeout_cap_s(self) -> float:
        """Hard sanity cap on job duration (seconds). 0 = no cap (default).

        Was hard-coded to 7200 (2h), which silently SIGKILLed long Ollama
        runs even when the user had configured a much longer ``--time-limit``.
        Now opt-in: set ``QUODEQ_JOB_TIMEOUT_S`` to a positive number to
        re-enable a wall-clock cap. Otherwise the watchdog only enforces
        the user-set ``deadline_at`` (with a grace window).
        """
        return float(os.environ.get("QUODEQ_JOB_TIMEOUT_S", "0"))

    def _watchdog_should_kill(self, job_id: str, started_at: float) -> bool:
        """Return True when the watchdog should SIGKILL the job process now."""
        now = time.time()
        cap = self._job_timeout_cap_s
        if cap > 0 and (now - started_at) > cap:
            return True
        job = self._store.get(job_id)
        deadline_at = getattr(job, "deadline_at", None) if job else None
        if not deadline_at:
            return False
        try:
            deadline = datetime.fromisoformat(deadline_at).timestamp()
        except (TypeError, ValueError):
            return False
        return now > deadline + _WATCHDOG_DEADLINE_GRACE_S

    def _monitor_process(self, job_id: str, process: subprocess.Popen) -> None:
        started_at = time.time()
        exit_code: int = 0
        while True:
            try:
                exit_code = process.wait(timeout=_WATCHDOG_POLL_INTERVAL_S)
                break
            except subprocess.TimeoutExpired:
                if self._watchdog_should_kill(job_id, started_at):
                    elapsed = int(time.time() - started_at)
                    _logger.warning("Job %s watchdog killing after %ds", job_id, elapsed)
                    process.kill()
                    try:
                        process.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
                    except subprocess.TimeoutExpired:
                        pass
                    exit_code = _EXIT_CODE_TIMEOUT
                    break
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
