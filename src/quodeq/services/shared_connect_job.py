"""Background connect job for the shared results repository.

Connecting clones the remote repo, which can take as long as the git
timeout, so PUT /api/shared/config claims a single process-wide connect slot,
runs ``connect_shared_repo`` on a daemon thread and answers 202. The UI polls
GET /api/shared/status, which reports this slot under ``connect``. Mirrors the
publish job in services/shared_publish.py.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from typing import Callable

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.services.github_access import forget_url
from quodeq.services.job_status import JobSlotStatus
from quodeq.services.shared_connect import ConnectOutcome, ConnectStatus, connect_shared_repo
from quodeq.services.shared_repo import RepoFormat, shared_evaluations_root, validate_remote_url
from quodeq.services.shared_listing import warm_shared_listing
from quodeq.services.sync_progress import SYNC_IDLE_FIELDS, WarmListing, progress_writer, read_projects
from quodeq.shared.fault_isolation import run_isolated

# Wire ``code`` values for a failed connect. The UI maps each to a
# translated message, so the strings are API contract.
CODE_INVALID_URL = "INVALID_URL"
CODE_CLONE_FAILED = "CLONE_FAILED"
CODE_FOREIGN_REPO = "FOREIGN_REPO"
CODE_UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
CODE_CONNECT_FAILED = "CONNECT_FAILED"

_PERCENT_DONE = 100

MESSAGE_CONNECT_UNEXPECTED = "An unexpected error occurred while connecting."
MESSAGE_CONNECT_START_FAILED = "Failed to start connect background job."


@dataclass(frozen=True)
class ConnectFailure:
    """A failed connect as the API reports it."""

    message: str
    code: str
    http_status: HTTPStatus


def invalid_url_failure(detail: str) -> ConnectFailure:
    """The failure for a URL ``validate_remote_url`` rejected with *detail*."""
    return ConnectFailure(detail, CODE_INVALID_URL, HTTPStatus.BAD_REQUEST)


def url_failure(url: str) -> ConnectFailure | None:
    """The failure for a *url* ``validate_remote_url`` rejects; None when it passes."""
    try:
        validate_remote_url(url)
    except ValueError as exc:
        return invalid_url_failure(str(exc))
    return None


def connect_failure(outcome: ConnectOutcome) -> ConnectFailure | None:
    """Map a failed *outcome* to its message, code and HTTP status; None on success."""
    if outcome.status == ConnectStatus.INVALID_URL:
        return invalid_url_failure(outcome.detail)
    if outcome.status == ConnectStatus.CLONE_FAILED:
        return ConnectFailure(
            f"could not clone the repository, check that git can access {outcome.url}",
            CODE_CLONE_FAILED,
            HTTPStatus.BAD_GATEWAY,
        )
    if outcome.status == RepoFormat.FOREIGN:
        return ConnectFailure(
            "the repository exists but does not look like a quodeq results repository",
            CODE_FOREIGN_REPO,
            HTTPStatus.BAD_REQUEST,
        )
    if outcome.status == RepoFormat.UNSUPPORTED_VERSION:
        return ConnectFailure(
            "this shared repository requires a newer version of quodeq",
            CODE_UNSUPPORTED_VERSION,
            HTTPStatus.BAD_REQUEST,
        )
    return None


class ConnectState(StrEnum):
    """The states a background connect job passes through."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class ConnectJobStatus(JobSlotStatus):
    """Lock-guarded connect job status: state, url, code, error, finished_at.

    Instantiable so tests get isolated status; production shares the
    module-default instance below, a single global connect slot.
    """

    def __init__(self) -> None:
        super().__init__(
            {
                "state": ConnectState.IDLE, "url": None, "code": None, "error": None,
                "finished_at": None, **SYNC_IDLE_FIELDS,
            },
            ConnectState.RUNNING,
        )

    def claim(self, url: str) -> bool:
        """Atomically take the connect slot; False when a connect is running."""
        return self.claim_slot(url=url, kind=SyncKind.CONNECT, phase=SyncPhase.CONNECTING)


_default_status = ConnectJobStatus()


def get_connect_status(status: ConnectJobStatus | None = None) -> dict:
    """Return a snapshot of the connect slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def is_connect_running(status: ConnectJobStatus | None = None) -> bool:
    """True while a connect job holds the slot."""
    return get_connect_status(status)["state"] == ConnectState.RUNNING


def _fail(status: ConnectJobStatus, message: str, code: str) -> None:
    status.set(state=ConnectState.ERROR, phase=SyncPhase.ERROR, code=code, error=message, finished_at=time.time())


def _do_connect(
    url: str, status: ConnectJobStatus, connect: Callable[..., ConnectOutcome] | None,
    log: LogSink, env: Mapping[str, str] | None = None, warm: WarmListing | None = None,
) -> None:
    outcome = (connect or connect_shared_repo)(url, log=log, env=env, progress=progress_writer(status))
    failure = connect_failure(outcome)
    if failure is not None:
        if failure.code == CODE_CLONE_FAILED:
            forget_url(url)  # a stale "reachable" cache entry must not outlive a failed clone
        _fail(status, failure.message, failure.code)
        return
    found = read_projects(
        shared_evaluations_root(url, env), url, status, warm=warm or warm_shared_listing, log=log,
    )
    status.set(
        state=ConnectState.DONE, phase=SyncPhase.DONE, percent=_PERCENT_DONE, projects_found=found,
        code=None, error=None, finished_at=time.time(),
    )


def run_connect_job(
    url: str, *, status: ConnectJobStatus,
    connect: Callable[..., ConnectOutcome] | None = None,
    log: LogSink = NULL_LOG, env: Mapping[str, str] | None = None,
    warm: WarmListing | None = None,
) -> None:
    """Connect to *url* and record the result in *status*.

    *connect* defaults to ``connect_shared_repo`` and *warm* (the READING
    phase's listing hydration) to ``warm_shared_listing``, both looked up at
    call time. An unexpected exception is logged and recorded as
    ``CONNECT_FAILED`` so the slot never stays stuck at running.
    """
    run_isolated(
        lambda: _do_connect(url, status, connect, log, env, warm),
        label="connect", log=log,
        on_error=lambda _exc: _fail(status, MESSAGE_CONNECT_UNEXPECTED, CODE_CONNECT_FAILED),
    )


class ConnectStartResult(StrEnum):
    """``start_connect``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"  # another connect holds the slot
    FAILED = "failed"  # the worker thread could not be started; the status carries the error


def _spawn_daemon(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


def start_connect(
    url: str, *,
    status: ConnectJobStatus | None = None,
    spawn: Callable[[Callable[[], None]], None] = _spawn_daemon,
    log: LogSink = NULL_LOG,
    env: Mapping[str, str] | None = None,
    warm: WarmListing | None = None,
) -> ConnectStartResult:
    """Kick off a background connect to *url*.

    *spawn* runs the job; the default starts a daemon thread, tests pass one
    that runs it inline. *log* receives the job's progress and failures. ``FAILED`` means the job could not be started.
    """
    status = status or _default_status
    if not status.claim(url):
        return ConnectStartResult.ALREADY_RUNNING
    try:
        spawn(lambda: run_connect_job(url, status=status, log=log, env=env, warm=warm))
    except RuntimeError as exc:
        _fail(status, MESSAGE_CONNECT_START_FAILED, CODE_CONNECT_FAILED)
        log.error(f"failed to start connect thread, {exc}")
        return ConnectStartResult.FAILED
    return ConnectStartResult.STARTED
