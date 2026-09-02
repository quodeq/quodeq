"""JobManager's log/marker parsing and background process-monitoring behavior.

Split from ``jobs.py`` to keep that file under the size ratchet's 300-line
cap. ``_JobMonitorMixin`` is mixed into ``JobManager`` there; it expects
``self._store``, ``self._lock``, ``self._reports_root``,
``self._run_log_writers``, ``self._pre_marker_buffer``, ``self._log``,
``self._processes``, ``self._on_job_complete``, and
``self._job_timeout_cap_s_override`` to already be set by
``JobManager.__init__`` -- all state ownership stays in ``jobs.py``, only
these methods moved.

Imported from ``jobs.py`` right before the ``JobManager`` class definition
(after that module's own constants are already assigned), so the
``from quodeq.services.jobs import ...`` below resolves against the
already-initialized part of that (still-loading) module; no true cycle.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from typing import Iterable

from quodeq.services._job_log_tee import consume_stream, drain_pre_marker_buffer, tee_run_log
from quodeq.services._job_model import Job, REPORT_PATH_RE, _ANSI_RE, _CC_MARKER_PREFIX, _MAX_COMPLETED_JOBS
from quodeq.services._job_watchdog import run_status_exit_reason, watchdog_should_kill
from quodeq.services.jobs import (
    STATUS_CANCELLED, STATUS_DONE, STATUS_FAILED, STATUS_RUNNING,
    _DEADLINE_EXIT_REASONS, _EXIT_CODE_TIMEOUT, _EXIT_REASON_DEADLINE,
    _REPORT_PATH_MARKER, _WATCHDOG_POLL_INTERVAL_S,
)
from quodeq.shared._env import env_float


class _JobMonitorMixin:
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
        elif phase in ("analyzing_start", "deadline_extended"):
            # deadline_extended: the pool auto-scale ratcheted the run
            # deadline forward; the watchdog must follow or it kills a
            # healthy run at the original deadline.
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
        consume_stream(
            job_id, stream,
            store=self._store, reports_root=self._reports_root,
            run_log_writers=self._run_log_writers, pre_marker_buffer=self._pre_marker_buffer,
            log=self._log, flush_batch=self._flush_batch,
        )

    def _drain_pre_marker_buffer(self, job_id: str) -> None:
        """Attempt to resolve run_dir and flush any buffered pre-marker lines.

        Called after the final ``_flush_batch`` so that lines buffered before
        the report_path marker are not lost when the marker arrives in the last
        batch of the stream.
        """
        drain_pre_marker_buffer(
            job_id,
            store=self._store, reports_root=self._reports_root,
            run_log_writers=self._run_log_writers, pre_marker_buffer=self._pre_marker_buffer,
        )

    def _tee_run_log(self, job_id: str, line: str) -> None:
        """Forward *line* to the job's run.log writer.

        Before the report_path marker arrives, ``run_dir`` is unknown — lines
        are held in ``self._pre_marker_buffer`` and flushed once the marker
        resolves the directory.

        Caller invariant: at most one ``_consume_stream`` runs per job_id at a
        time.  This method is not re-entrant for the same job_id.
        """
        tee_run_log(
            job_id, line,
            store=self._store, reports_root=self._reports_root,
            run_log_writers=self._run_log_writers, pre_marker_buffer=self._pre_marker_buffer,
        )

    def _evict_completed_jobs(self) -> None:
        """Remove oldest completed/failed/cancelled jobs beyond _MAX_COMPLETED_JOBS."""
        all_jobs = self._store.list()
        completed = [j for j in all_jobs if j.status != STATUS_RUNNING]
        excess = len(completed) - _MAX_COMPLETED_JOBS
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
        return env_float("QUODEQ_JOB_TIMEOUT_S", 0.0, minimum=0.0)

    def _watchdog_should_kill(self, job_id: str, started_at: float) -> bool:
        """Return True when the watchdog should SIGKILL the job process now."""
        return watchdog_should_kill(
            job_id, started_at, store=self._store, job_timeout_cap_s=self._job_timeout_cap_s,
        )

    def _run_status_exit_reason(self, job: Job | None) -> str | None:
        """Best-effort read of the run's ``status.json`` ``exit_reason``.

        The analysis loops break out at the deadline without raising, and the
        lifecycle records ``exit_reason="deadline"`` (see
        ``_cli_evaluation._record_deadline_if_hit``). When the process then
        exits nonzero without the job watchdog ever firing, this is the only
        signal that the exit was a time-limit truncation, not a failure.
        """
        return run_status_exit_reason(job, self._reports_root)

    def _classify_exit(self, job_id: str, exit_code: int, watchdog_killed: bool) -> str | None:
        """Resolve a time-limit ``deadline_reason``, or None for a plain exit.

        Called before the lock is taken in ``_monitor_process`` — status.json
        I/O must not block API request paths contending on self._lock.
        """
        if watchdog_killed:
            return _EXIT_REASON_DEADLINE
        if exit_code != 0:
            reason = self._run_status_exit_reason(self._store.get(job_id))
            if reason in _DEADLINE_EXIT_REASONS:
                return reason
        return None

    def _monitor_process(self, job_id: str, process: subprocess.Popen) -> None:
        started_at = time.time()
        exit_code: int = 0
        watchdog_killed = False
        while True:
            try:
                exit_code = process.wait(timeout=_WATCHDOG_POLL_INTERVAL_S)
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
                    # dir). _terminate_process matches the cancel/shutdown paths
                    # and waits internally.
                    # Deferred facade lookup: tests patch
                    # quodeq.services.jobs._terminate_process, so this must
                    # resolve dynamically through that module rather than a
                    # module-level import here.
                    from quodeq.services import jobs as _jobs_facade
                    _jobs_facade._terminate_process(process)
                    exit_code = _EXIT_CODE_TIMEOUT
                    watchdog_killed = True
                    break
        deadline_reason = self._classify_exit(job_id, exit_code, watchdog_killed)
        with self._lock:
            self._processes.pop(job_id, None)
            job = self._store.get(job_id)
            if not job or job.status == STATUS_CANCELLED:
                return
            job.exit_code = exit_code
            job.ended_at = datetime.now(timezone.utc).isoformat()
            if exit_code == 0:
                job.status = STATUS_DONE
            elif deadline_reason is not None:
                job.status = STATUS_CANCELLED
                job.exit_reason = deadline_reason
            else:
                job.status = STATUS_FAILED
            self._store.put(job)
            self._evict_completed_jobs()
        if self._on_job_complete is not None:
            try:
                self._on_job_complete(job_id, job)
            except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
                self._log.error(f"on_job_complete callback failed for {job_id}: {exc}")
