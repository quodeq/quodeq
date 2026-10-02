"""Background refresh job for the shared results repository.

Updating the local clone can take as long as the git timeout, so the refresh
route claims a single process-wide slot, runs the fetch on a daemon thread and
answers 202. The UI polls the status route, which reports this slot. Mirrors
services/shared_connect_job.py.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.services.job_spawn import spawn_daemon, start_claimed_job
from quodeq.services.job_status import JobSlotStatus
from quodeq.services.shared_listing import warm_shared_listing
from quodeq.services.shared_repo import refresh_shared_clone, shared_evaluations_root, sync_shared_index
from quodeq.services.sync_progress import SYNC_IDLE_FIELDS, WarmListing, progress_writer, read_projects
from quodeq.shared.fault_isolation import run_isolated

# Wire ``code`` values for a failed refresh; API contract.
CODE_REFRESH_FAILED = "REFRESH_FAILED"
CODE_REFRESH_UNEXPECTED = "REFRESH_UNEXPECTED"

MESSAGE_REFRESH_UNEXPECTED = "An unexpected error occurred while updating."
MESSAGE_REFRESH_START_FAILED = "Failed to start refresh background job."
MESSAGE_REFRESH_DEFAULT = "update failed"

_PERCENT_DONE = 100


class RefreshState(StrEnum):
    """The states a background refresh job passes through."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class RefreshStatus(JobSlotStatus):
    """Lock-guarded refresh job status: state, url, code, error, finished_at."""

    def __init__(self) -> None:
        super().__init__(
            {
                "state": RefreshState.IDLE, "url": None, "error": None, "code": None,
                "finished_at": None, **SYNC_IDLE_FIELDS,
            },
            RefreshState.RUNNING,
        )

    def claim(self, url: str) -> bool:
        """Atomically take the refresh slot; False when a refresh is running."""
        return self.claim_slot(url=url, kind=SyncKind.REFRESH, phase=SyncPhase.CONNECTING)


_default_status = RefreshStatus()


def get_refresh_status(status: RefreshStatus | None = None) -> dict:
    """Return a snapshot of the refresh slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def is_refresh_running(status: RefreshStatus | None = None) -> bool:
    """True while a refresh job holds the slot."""
    return get_refresh_status(status)["state"] == RefreshState.RUNNING


def _fail(status: RefreshStatus, message: str, code: str) -> None:
    status.set(state=RefreshState.ERROR, phase=SyncPhase.ERROR, code=code, error=message, finished_at=time.time())


@dataclass(frozen=True)
class RefreshSteps:
    """The refresh job's collaborators; each None means the real one, looked up at call time.

    *refresh* updates the clone (default ``refresh_shared_clone``),
    *sync_index* re-syncs the shared index (``sync_shared_index``), and
    *warm* hydrates the listing under READING (``warm_shared_listing``).
    """

    refresh: Callable[..., tuple[bool, str]] | None = None
    sync_index: Callable[[str], object] | None = None
    warm: WarmListing | None = None


def _do_refresh(
    url: str, status: RefreshStatus, steps: RefreshSteps, env: Mapping[str, str] | None, log: LogSink,
) -> None:
    ok, reason = (steps.refresh or refresh_shared_clone)(url, env, progress=progress_writer(status))
    if not ok:
        _fail(status, reason or MESSAGE_REFRESH_DEFAULT, CODE_REFRESH_FAILED)
        return
    (steps.sync_index or sync_shared_index)(url)
    found = read_projects(
        shared_evaluations_root(url, env), url, status, warm=steps.warm or warm_shared_listing, log=log,
    )
    status.set(
        state=RefreshState.DONE, phase=SyncPhase.DONE, percent=_PERCENT_DONE, projects_found=found,
        code=None, error=None, finished_at=time.time(),
    )


def run_refresh_job(
    url: str, *, status: RefreshStatus, env: Mapping[str, str] | None = None,
    steps: RefreshSteps | None = None, log: LogSink = NULL_LOG,
) -> None:
    """Refresh the clone of *url*, sync the index, and record the result in *status*.

    Before DONE the READING phase counts the projects and hydrates the
    listing so the list route answers from cache; see ``RefreshSteps`` for
    the injectable collaborators. An unexpected exception is logged and
    recorded as ``REFRESH_UNEXPECTED`` so the slot never stays stuck at running.
    """
    run_isolated(
        lambda: _do_refresh(url, status, steps or RefreshSteps(), env, log),
        label="refresh", log=log,
        on_error=lambda _exc: _fail(status, MESSAGE_REFRESH_UNEXPECTED, CODE_REFRESH_UNEXPECTED),
    )


class RefreshStartResult(StrEnum):
    """``start_refresh``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"  # the worker thread could not be started; the status carries the error


def start_refresh(
    url: str, *,
    status: RefreshStatus | None = None,
    spawn: Callable[[Callable[[], None]], None] = spawn_daemon,
    env: Mapping[str, str] | None = None,
    log: LogSink = NULL_LOG,
    steps: RefreshSteps | None = None,
) -> RefreshStartResult:
    """Kick off a background refresh of *url*; ``FAILED`` means it could not start."""
    status = status or _default_status
    outcome = start_claimed_job(
        status.claim(url), lambda: run_refresh_job(url, status=status, env=env, log=log, steps=steps),
        spawn=spawn, on_start_failed=lambda: _fail(status, MESSAGE_REFRESH_START_FAILED, CODE_REFRESH_UNEXPECTED), log=log, label="refresh",
    )
    return RefreshStartResult(outcome.value)
