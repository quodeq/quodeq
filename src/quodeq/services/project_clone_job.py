"""Background project-create job: clone, scan and register one project.

The route injects ``create``, which does the whole create-project call and
reports git progress and phases through the callbacks it is handed; this
module only owns the slot and its state machine. Mirrors
services/shared_pull_job.py.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.services.base import PhaseCallback, ProgressCallback
from quodeq.services.clone_codes import CODE_CLONE_UNKNOWN
from quodeq.services.job_spawn import spawn_daemon, start_claimed_job
from quodeq.services.job_status import JobSlotStatus
from quodeq.services.sync_progress import SYNC_IDLE_FIELDS
from quodeq.services.wiring_sync import ProgressUpdate
from quodeq.shared.fault_isolation import run_isolated

# Wire ``code`` values owned by the job itself; API contract.
CODE_CLONE_IN_PROGRESS = "CLONE_IN_PROGRESS"
CODE_CLONE_START_FAILED = "CLONE_START_FAILED"
CODE_CLONE_UNEXPECTED = "CLONE_UNEXPECTED"

MESSAGE_CLONE_DEFAULT = "clone failed"
MESSAGE_CLONE_UNEXPECTED = "An unexpected error occurred while adding the project."
MESSAGE_CLONE_START_FAILED = "Failed to start the add-project background job."

_PERCENT_DONE = 100


class CloneState(StrEnum):
    """The states a background clone job passes through."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class CloneOutcome:
    """What a create-project call produced: the project, or a coded failure."""

    ok: bool
    project_id: str | None = None
    project_name: str | None = None
    scan_data: dict | None = None
    error: str | None = None
    code: str | None = None
    detail: str = ""


class CloneStatus(JobSlotStatus):
    """Lock-guarded clone job status: state, repo, project, scan, code, error."""

    def __init__(self) -> None:
        super().__init__(
            {
                "state": CloneState.IDLE, "repo": None, "dest": None, "project_id": None,
                "project_name": None, "scan_data": None, "error": None, "code": None,
                "detail": None, "finished_at": None, **SYNC_IDLE_FIELDS,
            },
            CloneState.RUNNING,
        )

    def claim(self, repo: str, dest: str | None) -> bool:
        """Atomically take the clone slot; False when a clone is running."""
        return self.claim_slot(repo=repo, dest=dest, kind=SyncKind.CLONE, phase=SyncPhase.CONNECTING, percent=None)


_default_status = CloneStatus()


def get_clone_status(status: CloneStatus | None = None) -> dict:
    """Return a snapshot of the clone slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def is_clone_running(status: CloneStatus | None = None) -> bool:
    """True while a clone job holds the slot."""
    return get_clone_status(status)["state"] == CloneState.RUNNING


def _fail(status: CloneStatus, message: str, code: str, detail: str = "") -> None:
    status.set(
        state=CloneState.ERROR, phase=SyncPhase.ERROR, code=code, error=message,
        detail=detail, finished_at=time.time(),
    )


def _progress_writer(status: CloneStatus) -> ProgressCallback:
    def write(update: ProgressUpdate) -> None:
        status.set(phase=SyncPhase.DOWNLOADING, percent=update.percent, bytes=update.bytes)
    return write


def _phase_writer(status: CloneStatus) -> PhaseCallback:
    def write(phase: SyncPhase) -> None:
        status.set(phase=phase)
    return write


def _notify_done(on_done: Callable[[], None], log: LogSink) -> None:
    run_isolated(on_done, label="clone on_done", log=log)


def _do_clone(
    status: CloneStatus, create: Callable[[ProgressCallback, PhaseCallback], CloneOutcome],
    on_done: Callable[[], None] | None, log: LogSink,
) -> None:
    outcome = create(_progress_writer(status), _phase_writer(status))
    if not outcome.ok:
        _fail(status, outcome.error or MESSAGE_CLONE_DEFAULT, outcome.code or CODE_CLONE_UNKNOWN, outcome.detail)
        return
    status.set(
        state=CloneState.DONE, phase=SyncPhase.DONE, percent=_PERCENT_DONE,
        project_id=outcome.project_id, project_name=outcome.project_name, scan_data=outcome.scan_data,
        code=None, error=None, finished_at=time.time(),
    )
    if on_done is not None:
        _notify_done(on_done, log)  # the project exists; a failing hook must not downgrade the slot


def run_clone_job(
    status: CloneStatus, *, create: Callable[[ProgressCallback, PhaseCallback], CloneOutcome],
    on_done: Callable[[], None] | None = None, log: LogSink = NULL_LOG,
) -> None:
    """Run the create call and record the result in *status*.

    An unexpected exception is logged and recorded as ``CLONE_UNEXPECTED`` so
    the slot never stays stuck at running.
    """
    run_isolated(
        lambda: _do_clone(status, create, on_done, log),
        label="clone", log=log,
        on_error=lambda exc: _fail(status, MESSAGE_CLONE_UNEXPECTED, CODE_CLONE_UNEXPECTED, type(exc).__name__),
    )


class CloneStartResult(StrEnum):
    """``start_clone``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"  # the worker thread could not be started; the status carries the error


@dataclass(frozen=True)
class CloneHooks:
    """The clone job's collaborators: the create call, the done hook and the thread spawner.

    ``spawn=None`` means ``spawn_daemon``, looked up when the job starts so a test can swap it.
    """

    create: Callable[[ProgressCallback, PhaseCallback], CloneOutcome]
    on_done: Callable[[], None] | None = None
    spawn: Callable[[Callable[[], None]], None] | None = None


def start_clone(
    repo: str, dest: str | None, *, hooks: CloneHooks,
    status: CloneStatus | None = None, log: LogSink = NULL_LOG,
) -> CloneStartResult:
    """Kick off a background create of *repo*; ``FAILED`` means it could not start."""
    status = status or _default_status
    outcome = start_claimed_job(
        status.claim(repo, dest),
        lambda: run_clone_job(status, create=hooks.create, on_done=hooks.on_done, log=log),
        spawn=hooks.spawn or spawn_daemon,
        on_start_failed=lambda: _fail(status, MESSAGE_CLONE_START_FAILED, CODE_CLONE_START_FAILED),
        log=log, label="clone",
    )
    return CloneStartResult(outcome.value)
