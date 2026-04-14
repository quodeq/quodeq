"""Job data model, store protocol, and in-memory store implementation."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Protocol, runtime_checkable

from datetime import datetime, timezone

from quodeq.core.types import JobSnapshot
from quodeq.shared.constants import CC_MARKER_KEY

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

    def complete(self, exit_code: int, ended_at: str) -> None:
        """Transition job to a terminal state based on exit code."""
        self.exit_code = exit_code
        self.ended_at = ended_at
        self.status = "completed" if exit_code == 0 else "failed"

    def cancel(self, ended_at: str) -> None:
        """Mark job as cancelled."""
        if self.status in ("completed", "failed"):
            return
        self.status = "cancelled"
        self.ended_at = ended_at

    def add_log(self, line: str) -> None:
        """Append a log line to the rolling buffer."""
        self.logs.append(line)

    def set_phase(self, phase: str, dimension: str | None = None) -> None:
        """Update the current analysis phase."""
        self.phase = phase
        if dimension is not None:
            self.current_dimension = dimension

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
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


_logger = logging.getLogger(__name__)

_DEFAULT_PERSIST_DIR = Path.home() / ".quodeq" / "run" / "jobs"
_STALE_JOB_AGE_S = 24 * 60 * 60  # 24 hours


def _job_to_json(job: Job) -> dict:
    """Serialize a Job to a JSON-safe dict (no Process objects)."""
    return {
        "job_id": job.job_id,
        "status": job.status,
        "command": job.command,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "exit_code": job.exit_code,
        "logs": list(job.logs),
        "output_project": job.output_project,
        "output_run_id": job.output_run_id,
        "phase": job.phase,
        "current_dimension": job.current_dimension,
        "dimensions": job.dimensions,
    }


def _job_from_json(data: dict) -> Job:
    """Deserialize a Job from a JSON dict."""
    logs: deque[str] = deque(data.get("logs", []), maxlen=_MAX_LOG_LINES)
    return Job(
        job_id=data["job_id"],
        status=data["status"],
        command=data.get("command", []),
        started_at=data.get("started_at", ""),
        ended_at=data.get("ended_at"),
        exit_code=data.get("exit_code"),
        logs=logs,
        output_project=data.get("output_project"),
        output_run_id=data.get("output_run_id"),
        phase=data.get("phase"),
        current_dimension=data.get("current_dimension"),
        dimensions=data.get("dimensions"),
    )


class FileJobStore:
    """Job store backed by per-job JSON files on disk.

    Jobs are stored as ``{persist_dir}/{job_id}.json``.  All existing files
    are loaded on init, and stale completed/failed/cancelled jobs older than
    24 hours are cleaned up automatically.
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._persist_dir = persist_dir or _DEFAULT_PERSIST_DIR
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._load_all()
        self._cleanup_stale()

    # -- JobStore protocol ---------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
            self._write(job)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            path = self._persist_dir / f"{job_id}.json"
            path.unlink(missing_ok=True)

    # -- persistence helpers -------------------------------------------------

    def _write(self, job: Job) -> None:
        """Write a single job to disk. Caller must hold the lock."""
        path = self._persist_dir / f"{job.job_id}.json"
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(_job_to_json(job), indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            _logger.warning("Failed to persist job %s", job.job_id, exc_info=True)
            tmp.unlink(missing_ok=True)

    def _load_all(self) -> None:
        """Load every .json file in the persist dir."""
        for path in self._persist_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = _job_from_json(data)
                # Jobs that were 'running' when we crashed are effectively failed.
                if job.status == "running":
                    job.status = "failed"
                    job.exit_code = -1
                    self._jobs[job.job_id] = job
                    self._write(job)
                else:
                    self._jobs[job.job_id] = job
            except (json.JSONDecodeError, KeyError, OSError):
                _logger.warning("Skipping corrupt job file %s", path, exc_info=True)

    def _cleanup_stale(self) -> None:
        """Remove completed/failed/cancelled jobs older than 24 hours."""
        now = time.time()
        stale_ids: list[str] = []
        for job in self._jobs.values():
            if job.status == "running":
                continue
            if not job.ended_at:
                continue
            try:
                ended = datetime.fromisoformat(job.ended_at)
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=timezone.utc)
                age = now - ended.timestamp()
                if age > _STALE_JOB_AGE_S:
                    stale_ids.append(job.job_id)
            except (ValueError, TypeError):
                continue
        for jid in stale_ids:
            _logger.info("Cleaning up stale job %s", jid)
            self._jobs.pop(jid, None)
            (self._persist_dir / f"{jid}.json").unlink(missing_ok=True)


def create_job_store() -> JobStore:
    """Create the default job store.

    Returns a ``FileJobStore`` that persists jobs to ``~/.quodeq/run/jobs/``
    so that job state survives server restarts.
    """
    return FileJobStore()
