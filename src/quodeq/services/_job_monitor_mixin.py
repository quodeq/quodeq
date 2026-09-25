"""JobManager's log/marker parsing and background process-monitoring behavior.

``JobMonitorMixin`` is mixed into ``JobManager`` (``jobs.py``); the state it
reads is declared on the class below and owned by ``JobManager.__init__``,
which assigns every one of those attributes.

The constants both modules need live in ``_job_model``, which imports
neither, so nothing here imports ``jobs``.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from quodeq.shared.clock import utc_now_iso
from quodeq.config.services_env import job_timeout_cap_s as _resolve_job_timeout_cap_s
from quodeq.services._job_log_tee import TeeContext, consume_stream, drain_pre_marker_buffer, tee_run_log
from quodeq.services._job_model import (
    Job, JobStore, REPORT_PATH_RE,
    ANSI_RE, CC_MARKER_PREFIX, EXIT_CODE_TIMEOUT,
    MAX_COMPLETED_JOBS, REPORT_PATH_MARKER,
    WATCHDOG_POLL_INTERVAL_S,
)
from quodeq.services._job_watchdog import run_status_exit_reason, watchdog_should_kill
from quodeq.core.observability import LogSink
from quodeq.core.run.exit_reason import DEADLINE_EXIT_REASONS, ExitReason
from quodeq.core.run.job_status import JobStatus
from quodeq.core.stream.events import COPILOT_MCP_POLICY_REASON
from quodeq.shared.run_log import RunLogWriter
from quodeq.shared.constants import (
    CC_PHASE_ANALYZING, CC_PHASE_ANALYZING_START, CC_PHASE_DEADLINE_EXTENDED,
    CC_PHASE_REPORT_PATH, CC_PHASE_SCORING, CC_PHASE_SETUP,
)


class JobMonitorMixin:
    """Log/marker parsing and process monitoring for ``JobManager``.

    The attributes below are declared, not assigned: ``JobManager.__init__``
    owns every one of them. Declaring them here is what makes this class
    readable on its own and lets a type checker catch a rename on either
    side.
    """

    _store: JobStore
    _lock: threading.Lock
    _reports_root: Path | None
    _run_log_writers: dict[str, RunLogWriter]
    _pre_marker_buffer: dict[str, list[str]]
    _log: LogSink
    _processes: dict[str, Any]
    _on_job_complete: Callable[[str, Job], None] | None
    _job_timeout_cap_s_override: float | None
    _watchdog_grace_s: float

    def _apply_marker(self, job: Job, line: str) -> None:
        """Parse a structured JSON marker and update job state."""
        try:
            marker = json.loads(line)
        except json.JSONDecodeError:
            self._log.warning(f"malformed structured marker: {line!r}")
            return
        phase = marker.get("_cc")
        if phase == CC_PHASE_SETUP:
            job.phase = CC_PHASE_SETUP
            job.dimensions = marker.get("dimensions")
        elif phase in (CC_PHASE_ANALYZING, CC_PHASE_SCORING):
            job.current_dimension = marker.get("dimension")
            job.phase = phase
        elif phase in (CC_PHASE_ANALYZING_START, CC_PHASE_DEADLINE_EXTENDED):
            # deadline_extended: the pool auto-scale ratcheted the run
            # deadline forward; the watchdog must follow or it kills a
            # healthy run at the original deadline.
            job.deadline_at = marker.get("deadline_at")
        elif phase == CC_PHASE_REPORT_PATH:
            project = marker.get("project")
            run_id = marker.get("runId")
            if project and run_id:
                job.output_project = project
                job.output_run_id = run_id

    def _append_log(self, job: Job, line: str) -> None:
        if not line:
            return
        if line.startswith(CC_MARKER_PREFIX):
            self._apply_marker(job, line)
            return
        job.logs.append(ANSI_RE.sub("", line))
        # Fallback: extract report path from log text if the structured
        # marker was not received (backward compat with older pipelines).
        if not job.output_project and REPORT_PATH_MARKER in line:
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

    @property
    def _tee_ctx(self) -> TeeContext:
        return TeeContext(
            store=self._store, reports_root=self._reports_root,
            run_log_writers=self._run_log_writers, pre_marker_buffer=self._pre_marker_buffer,
            log=self._log, flush_batch=self._flush_batch,
        )

    def _consume_stream(self, job_id: str, stream: Iterable[str] | None) -> None:
        consume_stream(job_id, stream, self._tee_ctx)

    def _drain_pre_marker_buffer(self, job_id: str) -> None:
        """Attempt to resolve run_dir and flush any buffered pre-marker lines.

        Called after the final ``_flush_batch`` so that lines buffered before
        the report_path marker are not lost when the marker arrives in the last
        batch of the stream.
        """
        drain_pre_marker_buffer(job_id, self._tee_ctx)

    def _tee_run_log(self, job_id: str, line: str) -> None:
        """Forward *line* to the job's run.log writer.

        Before the report_path marker arrives, ``run_dir`` is unknown — lines
        are held in ``self._pre_marker_buffer`` and flushed once the marker
        resolves the directory.

        Caller invariant: at most one ``_consume_stream`` runs per job_id at a
        time.  This method is not re-entrant for the same job_id.
        """
        tee_run_log(job_id, line, self._tee_ctx)

    def _evict_completed_jobs(self) -> None:
        """Remove oldest completed/failed/cancelled jobs beyond MAX_COMPLETED_JOBS."""
        all_jobs = self._store.list()
        completed = [j for j in all_jobs if j.status != JobStatus.RUNNING]
        excess = len(completed) - MAX_COMPLETED_JOBS
        if excess > 0:
            # Oldest first, or a store wedged with old junk would evict the
            # user's newest real runs while the junk survived.
            completed.sort(key=lambda j: j.ended_at or j.started_at or "")
            for job in completed[:excess]:
                self._store.delete(job.job_id)

    @property
    def _job_timeout_cap_s(self) -> float:
        """Hard sanity cap on job duration (seconds). 0 = no cap (default).

        Was hard-coded to 7200 (2h), which silently SIGKILLed long Ollama
        runs even when the user had configured a much longer ``--time-limit``.
        Now opt-in: pass ``job_timeout_cap_s`` to the constructor, or set
        ``QUODEQ_JOB_TIMEOUT_S`` to a positive number to re-enable a
        wall-clock cap that way. Otherwise the watchdog only enforces the
        user-set ``deadline_at`` (with a grace window).
        """
        if self._job_timeout_cap_s_override is not None:
            return self._job_timeout_cap_s_override
        return _resolve_job_timeout_cap_s()

    def _watchdog_should_kill(self, job_id: str, started_at: float) -> bool:
        """Return True when the watchdog should SIGKILL the job process now."""
        return watchdog_should_kill(
            job_id, started_at, store=self._store, job_timeout_cap_s=self._job_timeout_cap_s,
            grace_s=self._watchdog_grace_s,
        )

    def _run_status_exit_reason(self, job: Job | None) -> str | None:
        """Delegate to ``_job_watchdog.run_status_exit_reason`` (which says why it exists)."""
        return run_status_exit_reason(job, self._reports_root)

    def _classify_exit(self, job_id: str, exit_code: int, watchdog_killed: bool) -> str | None:
        """Resolve a deadline or Copilot policy reason, or None for a plain exit.

        Called before the lock is taken in ``_monitor_process`` — status.json
        I/O must not block API request paths contending on self._lock.
        """
        if watchdog_killed:
            return ExitReason.DEADLINE
        reason = self._run_status_exit_reason(self._store.get(job_id))
        if reason == COPILOT_MCP_POLICY_REASON or (exit_code != 0 and reason in DEADLINE_EXIT_REASONS):
            return reason
        return None

    def _monitor_process(self, job_id: str, process: subprocess.Popen) -> None:
        started_at = time.time()
        exit_code: int = 0
        watchdog_killed = False
        while True:
            try:
                exit_code = process.wait(timeout=WATCHDOG_POLL_INTERVAL_S)
                break
            except subprocess.TimeoutExpired:
                if self._watchdog_should_kill(job_id, started_at):
                    elapsed = int(time.time() - started_at)
                    self._log.warning(f"Job {job_id} watchdog killing after {elapsed}s")
                    # Kill the whole process GROUP (TERM -> grace -> KILL), not
                    # just the parent PID. The subprocess is spawned
                    # start_new_session=True, so a bare process.kill() would
                    # orphan the subagent pool + AI-CLI children (leaking tokens
                    # and CPU, and letting them write into the abandoned run
                    # dir). ``self._terminate`` (JobManager, jobs.py) matches
                    # the cancel/shutdown paths and waits internally; tests
                    # patch quodeq.services.jobs.terminate_process, which
                    # _terminate's own module-global lookup still picks up.
                    self._terminate(process)
                    exit_code = EXIT_CODE_TIMEOUT
                    watchdog_killed = True
                    break
        exit_reason = self._classify_exit(job_id, exit_code, watchdog_killed)
        with self._lock:
            self._processes.pop(job_id, None)
            job = self._store.get(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            job.exit_code = exit_code
            job.exit_reason = exit_reason
            job.ended_at = utc_now_iso()
            if exit_code == 0:
                job.status = JobStatus.DONE
            elif exit_reason in DEADLINE_EXIT_REASONS:
                job.status = JobStatus.CANCELLED
            else:
                job.status = JobStatus.FAILED
            self._store.put(job)
            self._evict_completed_jobs()
        if self._on_job_complete is not None:
            try:
                self._on_job_complete(job_id, job)
            except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
                self._log.error(f"on_job_complete callback failed for {job_id}: {exc}")
