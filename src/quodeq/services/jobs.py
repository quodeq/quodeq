"""Background job management for evaluation subprocesses."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

import logging
import subprocess

from quodeq.core.types import JobSnapshot
from quodeq.engine.runner import CC_MARKER_KEY

_logger = logging.getLogger(__name__)

_MAX_LOG_LINES = 600  # rolling buffer size for per-job log lines
_MAX_COMPLETED_JOBS = 100  # max completed/failed/cancelled jobs to retain
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
_CC_MARKER_PREFIX = '{"' + CC_MARKER_KEY
_CONSUME_BATCH_SIZE = 1
REPORT_PATH_RE = re.compile(r"Report path:.*[/\\]([^/\\\s]+)[/\\]([^/\\\s]+)[/\\]evaluation")


@dataclass
class Job:
    """State of a single evaluation subprocess."""

    job_id: str
    status: str
    command: list[str]
    started_at: str
    ended_at: str | None
    exit_code: int | None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_LOG_LINES))
    output_project: str | None = None
    output_run_id: str | None = None
    phase: str | None = None
    current_dimension: str | None = None
    dimensions: list[str] | None = None

    def to_dict(self) -> JobSnapshot:
        """Return a frozen snapshot of the current job state."""
        return JobSnapshot(
            job_id=self.job_id,
            status=self.status,
            command=Path(self.command[0]).name if self.command else "",
            started_at=self.started_at,
            ended_at=self.ended_at,
            exit_code=self.exit_code,
            logs=list(self.logs),
            output_project=self.output_project,
            output_run_id=self.output_run_id,
            phase=self.phase,
            current_dimension=self.current_dimension,
            dimensions=self.dimensions,
        )


@runtime_checkable
class JobStore(Protocol):
    """Abstraction for persisting job state.

    The default ``InMemoryJobStore`` keeps jobs in a process-local dict.
    Replace with a database- or Redis-backed implementation for multi-worker
    deployments where job state must survive restarts and be shared across
    processes.
    """

    def get(self, job_id: str) -> Job | None:
        """Return the job with the given ID, or None."""
        ...

    def put(self, job: Job) -> None:
        """Insert or update a job."""
        ...

    def list(self) -> list[Job]:
        """Return all tracked jobs."""
        ...

    def delete(self, job_id: str) -> None:
        """Remove a job by ID (no-op if not found)."""
        ...


class InMemoryJobStore:
    """Process-local job store backed by a plain dict.

    .. warning::

       All job state lives in process memory and is lost on restart.
       This store cannot be shared across workers or processes.

    For multi-worker deployments, implement the ``JobStore`` protocol
    with a persistent backend (e.g. database, Redis) and pass it to
    ``JobManager`` via the ``job_store`` parameter, or override
    ``create_job_store``.
    """
    # See https://github.com/anthropics/quodeq/issues/42 for persistent adapter plans.

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def put(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    def list(self) -> list[Job]:
        return list(self._jobs.values())

    def delete(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)


def create_job_store() -> JobStore:
    """Create the default job store.

    Override this factory to plug in a persistent backend for multi-worker
    deployments.  The returned object must satisfy the ``JobStore`` protocol.
    """
    return InMemoryJobStore()


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
            status="running",
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
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _logger.error("Failed to start job subprocess: %s", exc)
            job.status = "failed"
            job.ended_at = datetime.now(timezone.utc).isoformat()
            job.exit_code = -1
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

    def cancel_job(self, job_id: str) -> bool:
        """Terminate a running job. Return True if cancelled successfully."""
        with self._lock:
            job = self._store.get(job_id)
            process = self._processes.get(job_id)
            if not job or job.status != "running":
                return False
            job.status = "cancelled"
            job.ended_at = datetime.now(timezone.utc).isoformat()
            self._store.put(job)
        if process:
            process.terminate()
        return True

    def get_job(self, job_id: str) -> JobSnapshot | None:
        """Return the current state of a job, or None if not found."""
        with self._lock:
            job = self._store.get(job_id)
            if not job:
                return None
            return job.to_dict()

    def list_jobs(self) -> list[JobSnapshot]:
        """Return all tracked jobs as frozen snapshots."""
        with self._lock:
            return [job.to_dict() for job in self._store.list()]

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

    def _append_log(self, job: Job, line: str) -> None:
        if not line:
            return
        if line.startswith(_CC_MARKER_PREFIX):
            self._apply_marker(job, line)
            return
        job.logs.append(_ANSI_RE.sub("", line))
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
        completed = [j.job_id for j in all_jobs if j.status != "running"]
        excess = len(completed) - _MAX_COMPLETED_JOBS
        if excess > 0:
            for jid in completed[:excess]:
                self._store.delete(jid)

    def _monitor_process(self, job_id: str, process: subprocess.Popen) -> None:
        exit_code = process.wait()
        with self._lock:
            self._processes.pop(job_id, None)
            job = self._store.get(job_id)
            if not job or job.status == "cancelled":
                return
            job.exit_code = exit_code
            job.ended_at = datetime.now(timezone.utc).isoformat()
            job.status = "done" if exit_code == 0 else "failed"
            self._store.put(job)
            self._evict_completed_jobs()
        if self._on_job_complete is not None:
            try:
                self._on_job_complete(job_id, job)
            except (OSError, ValueError, TypeError, RuntimeError, KeyError) as exc:
                _logger.error("on_job_complete callback failed for %s: %s", job_id, exc)
