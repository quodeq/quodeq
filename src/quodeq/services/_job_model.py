"""Job data model, store protocol, and in-memory store implementation.

JSON serialization (``_job_to_json``/``_job_from_json``) and the disk-backed
``FileJobStore``/``create_job_store`` live in ``_job_file_store.py`` -- split
out to keep this module under the size ratchet's 300-line cap, and
re-exported from here.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import TYPE_CHECKING, Callable, Protocol, runtime_checkable

from quodeq.core.types import JobSnapshot
from quodeq.shared.constants import CC_MARKER_KEY

_REPORT_PATH_MARKER = "Report path:"
_EXIT_CODE_TIMEOUT = -9

# Watchdog polls process state every N seconds and re-checks deadline_at,
# which only lands in job state after the analyzing_start marker -- so a
# blocking wait(timeout=full_budget) at spawn time can't see it.
_WATCHDOG_POLL_INTERVAL_S = 1.0

# status.json exit reasons that mean "the run hit its time budget" -- the
# user's own setting doing its job, not an error. Jobs ending this way are
# marked cancelled (already in the salvage-scoring trigger list in
# api/_evaluation_routes.py) with exit_reason set, so the evaluate header
# renders "time limit reached" instead of FAILED.
_DEADLINE_EXIT_REASONS = ("deadline", "time_limit")
_EXIT_REASON_DEADLINE = "deadline"

if TYPE_CHECKING:
    import subprocess

    from quodeq.services._external_jobs import ProcessControl

# Canonical job status strings. They live here, with the Job they describe,
# so both jobs.py (which re-exports them for its importers) and the mixins
# it composes can import them without reaching back into jobs.py.
STATUS_RUNNING = "running"
STATUS_CANCELLED = "cancelled"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

_MAX_LOG_LINES = 600  # rolling buffer size for per-job log lines
_MAX_COMPLETED_JOBS = 100  # max completed/failed/cancelled jobs to retain
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHF]")
_CC_MARKER_PREFIX = '{"' + CC_MARKER_KEY
REPORT_PATH_RE = re.compile(r"Report path:.*[/\\]([^/\\\s]+)[/\\]([^/\\\s]+)[/\\]evaluation")


@dataclass(frozen=True, slots=True)
class JobLaunchOptions:
    """How ``JobManager.start_job`` spawns a command and what it records on the job.

    ``cwd``/``env`` go to the subprocess; ``ai_provider``, ``ai_model`` and
    ``time_limit_s`` are stored on the job so status readers (progress route,
    UI) can report the run's client and budget.
    """
    cwd: str | None = None
    env: dict[str, str] | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    time_limit_s: int | None = None


def new_job(job_id: str, cmd: list[str], launch: JobLaunchOptions, *, status: str) -> "Job":
    """A fresh job record for *cmd*, started now, carrying *launch*'s run metadata."""
    from datetime import datetime, timezone  # noqa: PLC0415

    return Job(
        job_id=job_id,
        status=status,
        command=cmd,
        started_at=datetime.now(timezone.utc).isoformat(),
        ended_at=None,
        exit_code=None,
        ai_provider=launch.ai_provider,
        ai_model=launch.ai_model,
        time_limit_s=launch.time_limit_s,
    )


def mark_spawn_failed(job: "Job", exc: BaseException, *, status: str, exit_code: int) -> None:
    """Close *job* as failed-to-start: terminal status, end time, exit code and a log line."""
    from datetime import datetime, timezone  # noqa: PLC0415

    job.status = status
    job.ended_at = datetime.now(timezone.utc).isoformat()
    job.exit_code = exit_code
    job.logs.append(f"Failed to start process: {exc}")


@dataclass(frozen=True, slots=True)
class JobProcessSeams:
    """Injection points for how ``JobManager`` spawns, probes and caps subprocesses.

    Every field defaults to the production collaborator: ``subprocess.Popen``,
    the signal-based ``ProcessControl``, and the ``QUODEQ_JOB_TIMEOUT_S``
    env var for the hard duration cap.
    """
    spawn_impl: Callable[..., subprocess.Popen] | None = None
    process_control: ProcessControl | None = None
    job_timeout_cap_s: float | None = None


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
    deadline_at: str | None = None
    current_dimension: str | None = None
    dimensions: list[str] | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    time_limit_s: int | None = None  # 0 = unlimited, None = unknown
    # Why the job ended ("deadline", "time_limit", ...); None for clean
    # completions and plain failures. Lets the UI tell a time-budget kill
    # apart from a real failure.
    exit_reason: str | None = None

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
            deadline_at=self.deadline_at,
            current_dimension=self.current_dimension,
            dimensions=self.dimensions,
            ai_provider=self.ai_provider,
            ai_model=self.ai_model,
            time_limit_s=self.time_limit_s,
            exit_reason=self.exit_reason,
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
