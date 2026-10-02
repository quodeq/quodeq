"""Background pull job: import one project from the shared repository.

The route injects ``pull``, which builds and imports the project's zip; this
module only owns the slot and its state machine. Mirrors
services/shared_connect_job.py.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.services.job_status import JobSlotStatus
from quodeq.services.sync_progress import SYNC_IDLE_FIELDS
from quodeq.shared.fault_isolation import run_isolated

# Wire ``code`` values for a failed pull; API contract.
CODE_PULL_FAILED = "PULL_FAILED"
CODE_PULL_UNEXPECTED = "PULL_UNEXPECTED"

MESSAGE_PULL_DEFAULT = "pull failed"
MESSAGE_PULL_UNEXPECTED = "An unexpected error occurred while pulling."
MESSAGE_PULL_START_FAILED = "Failed to start pull background job."

_PERCENT_DONE = 100


@dataclass(frozen=True)
class PullOutcome:
    """What a pull produced: the imported project, or a coded failure."""

    ok: bool
    project_id: str | None = None
    project_name: str | None = None
    renamed: bool = False
    code: str | None = None
    error: str | None = None


class PullState(StrEnum):
    """The states a background pull job passes through."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class PullStatus(JobSlotStatus):
    """Lock-guarded pull job status: state, project, ids, code, error."""

    def __init__(self) -> None:
        super().__init__(
            {
                "state": PullState.IDLE, "project": None, "project_id": None, "project_name": None,
                "renamed": None, "error": None, "code": None, "finished_at": None, **SYNC_IDLE_FIELDS,
            },
            PullState.RUNNING,
        )

    def claim(self, project: str) -> bool:
        """Atomically take the pull slot; False when a pull is running."""
        return self.claim_slot(project=project, kind=SyncKind.PULL, phase=SyncPhase.DOWNLOADING, percent=None)


_default_status = PullStatus()


def get_pull_status(status: PullStatus | None = None) -> dict:
    """Return a snapshot of the pull slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def is_pull_running(status: PullStatus | None = None) -> bool:
    """True while a pull job holds the slot."""
    return get_pull_status(status)["state"] == PullState.RUNNING


def _fail(status: PullStatus, message: str, code: str) -> None:
    status.set(state=PullState.ERROR, phase=SyncPhase.ERROR, code=code, error=message, finished_at=time.time())


def _notify_done(on_done: Callable[[], None], log: LogSink) -> None:
    run_isolated(on_done, label="pull on_done", log=log)


def _do_pull(
    project: str, status: PullStatus, pull: Callable[[str], PullOutcome],
    on_done: Callable[[], None] | None, log: LogSink,
) -> None:
    status.set(phase=SyncPhase.DOWNLOADING, percent=None)
    outcome = pull(project)
    if not outcome.ok:
        _fail(status, outcome.error or MESSAGE_PULL_DEFAULT, outcome.code or CODE_PULL_FAILED)
        return
    status.set(
        state=PullState.DONE, phase=SyncPhase.DONE, percent=_PERCENT_DONE,
        project_id=outcome.project_id, project_name=outcome.project_name, renamed=outcome.renamed,
        code=None, error=None, finished_at=time.time(),
    )
    if on_done is not None:
        _notify_done(on_done, log)  # the import is done; a failing hook must not downgrade the slot


def run_pull_job(
    project: str, *, status: PullStatus, pull: Callable[[str], PullOutcome],
    on_done: Callable[[], None] | None = None, log: LogSink = NULL_LOG,
) -> None:
    """Pull *project* and record the result in *status*.

    An unexpected exception is logged and recorded as ``PULL_UNEXPECTED`` so
    the slot never stays stuck at running.
    """
    run_isolated(
        lambda: _do_pull(project, status, pull, on_done, log),
        label="pull", log=log,
        on_error=lambda _exc: _fail(status, MESSAGE_PULL_UNEXPECTED, CODE_PULL_UNEXPECTED),
    )


class PullStartResult(StrEnum):
    """``start_pull``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"  # the worker thread could not be started; the status carries the error


def _spawn_daemon(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


def start_pull(
    project: str, *, pull: Callable[[str], PullOutcome],
    status: PullStatus | None = None,
    spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
    on_done: Callable[[], None] | None = None,
    log: LogSink = NULL_LOG,
) -> PullStartResult:
    """Kick off a background pull of *project*; ``FAILED`` means it could not start."""
    status = status or _default_status
    if not status.claim(project):
        return PullStartResult.ALREADY_RUNNING
    try:
        spawn(lambda: run_pull_job(project, status=status, pull=pull, on_done=on_done, log=log))
    except RuntimeError as exc:
        _fail(status, MESSAGE_PULL_START_FAILED, CODE_PULL_UNEXPECTED)
        log.error(f"failed to start pull thread, {exc}")
        return PullStartResult.FAILED
    return PullStartResult.STARTED
