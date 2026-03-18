"""Job data model, store protocol, and in-memory store implementation."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Protocol, runtime_checkable

from quodeq.core.types import JobSnapshot
from quodeq.engine._runner_markers import CC_MARKER_KEY

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


def create_job_store() -> JobStore:
    """Create the default job store.

    Override this factory to plug in a persistent backend for multi-worker
    deployments.  The returned object must satisfy the ``JobStore`` protocol.
    """
    return InMemoryJobStore()
