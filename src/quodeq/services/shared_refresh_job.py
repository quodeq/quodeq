"""Background refresh job for the shared results repository.

Updating the local clone can take as long as the git timeout, so the refresh
route claims a single process-wide slot, runs the fetch on a daemon thread and
answers 202. The UI polls the status route, which reports this slot. Mirrors
services/shared_connect_job.py.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from enum import StrEnum
from typing import Callable

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.services.job_status import JobSlotStatus
from quodeq.services.shared_repo import refresh_shared_clone, sync_shared_index
from quodeq.services.sync_progress import SYNC_IDLE_FIELDS, progress_writer
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


def _do_refresh(
    url: str, status: RefreshStatus, refresh: Callable[..., tuple[bool, str]] | None,
    sync_index: Callable[[str], object] | None, env: Mapping[str, str] | None,
) -> None:
    do_refresh = refresh or refresh_shared_clone
    do_sync = sync_index or sync_shared_index
    ok, reason = do_refresh(url, env, progress=progress_writer(status))
    if not ok:
        _fail(status, reason or MESSAGE_REFRESH_DEFAULT, CODE_REFRESH_FAILED)
        return
    do_sync(url)
    status.set(
        state=RefreshState.DONE, phase=SyncPhase.DONE, percent=_PERCENT_DONE,
        code=None, error=None, finished_at=time.time(),
    )


def run_refresh_job(
    url: str, *, status: RefreshStatus, env: Mapping[str, str] | None = None,
    refresh: Callable[..., tuple[bool, str]] | None = None,
    sync_index: Callable[[str], object] | None = None,
    log: LogSink = NULL_LOG,
) -> None:
    """Refresh the clone of *url*, sync the index, and record the result in *status*.

    An unexpected exception is logged and recorded as ``REFRESH_UNEXPECTED``
    so the slot never stays stuck at running.
    """
    run_isolated(
        lambda: _do_refresh(url, status, refresh, sync_index, env),
        label="refresh", log=log,
        on_error=lambda _exc: _fail(status, MESSAGE_REFRESH_UNEXPECTED, CODE_REFRESH_UNEXPECTED),
    )


class RefreshStartResult(StrEnum):
    """``start_refresh``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"  # the worker thread could not be started; the status carries the error


def _spawn_daemon(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


def start_refresh(
    url: str, *,
    status: RefreshStatus | None = None,
    spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
    env: Mapping[str, str] | None = None,
    log: LogSink = NULL_LOG,
) -> RefreshStartResult:
    """Kick off a background refresh of *url*; ``FAILED`` means it could not start."""
    status = status or _default_status
    if not status.claim(url):
        return RefreshStartResult.ALREADY_RUNNING
    try:
        spawn(lambda: run_refresh_job(url, status=status, env=env, log=log))
    except RuntimeError as exc:
        _fail(status, MESSAGE_REFRESH_START_FAILED, CODE_REFRESH_UNEXPECTED)
        log.error(f"failed to start refresh thread, {exc}")
        return RefreshStartResult.FAILED
    return RefreshStartResult.STARTED
