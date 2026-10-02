"""Background GitHub device-flow job: one process-wide slot, polled by the UI.

Mirrors services/shared_connect_job.py: POST /api/github/device-flow claims
the slot, asks GitHub for a user code, answers 202 with it and polls GitHub
on a daemon thread until the user approves, the code expires, or GitHub
refuses. GET /api/github/device-flow snapshots the slot.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from quodeq.config.github_account import GitHubAccount, TokenMethod, store_account
from quodeq.config.github_app import GITHUB_OAUTH_SCOPE, github_client_id
from quodeq.services.github_access import clear_access_cache
from quodeq.services.github_oauth_client import (
    DeviceCode, GitHubOAuthClient, GitHubRefused, GitHubUnreachable, PollKind, TokenGrant,
)
from quodeq.services.job_status import JobSlotStatus
from quodeq.shared.fault_isolation import run_isolated
from quodeq.shared.log_sink import SHARED_LOG

SLOW_DOWN_EXTRA_S = 5
MESSAGE_FLOW_UNEXPECTED = "An unexpected error occurred while signing in."
MESSAGE_GITHUB_UNREACHABLE = "GitHub could not be reached."
MESSAGE_GITHUB_REFUSED = "GitHub refused the request (HTTP {status})."
MESSAGE_START_FAILED = "Failed to start the sign-in background job."


class DeviceFlowState(StrEnum):
    """The states a sign-in passes through."""

    IDLE = "idle"
    AWAITING_USER = "awaiting_user"
    DONE = "done"
    EXPIRED = "expired"
    DENIED = "denied"
    ERROR = "error"


class StartResult(StrEnum):
    """``start_device_flow``'s return value."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    NOT_CONFIGURED = "not_configured"  # empty client id: the OAuth App is not registered
    UNREACHABLE = "unreachable"  # GitHub did not answer the device-code request
    REFUSED = "refused"  # GitHub answered 4xx to the device-code request; usually a bad or unregistered client id
    FAILED = "failed"  # the worker thread could not be started


_TERMINAL = {
    PollKind.EXPIRED: DeviceFlowState.EXPIRED,
    PollKind.DENIED: DeviceFlowState.DENIED,
    PollKind.FAILED: DeviceFlowState.ERROR,
}


class DeviceFlowStatus(JobSlotStatus):
    """Lock-guarded sign-in slot; production shares the module default."""

    def __init__(self) -> None:
        super().__init__(
            {
                "state": DeviceFlowState.IDLE, "user_code": None, "verification_uri": None,
                "expires_in": None, "interval": None, "login": None, "error": None, "finished_at": None,
            },
            DeviceFlowState.AWAITING_USER,
        )


_default_status = DeviceFlowStatus()


@dataclass(frozen=True)
class FlowDeps:
    """Injectable collaborators; None resolves to production."""

    client: GitHubOAuthClient | None = None
    client_id: str | None = None
    store: Callable[[GitHubAccount], tuple[bool, bool]] | None = None
    spawn: Callable[[Callable[[], None]], None] | None = None
    sleep: Callable[[float], None] | None = None
    now: Callable[[], float] | None = None
    on_signed_in: Callable[[], None] | None = None


def _spawn_daemon(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


def get_device_flow_status(status: DeviceFlowStatus | None = None) -> dict:
    """Snapshot of the sign-in slot, defaulting to the module-wide one."""
    return (status or _default_status).copy()


def _finish(status: DeviceFlowStatus, state: DeviceFlowState, now: Callable[[], float], **fields) -> None:
    status.set(state=state, finished_at=now(), **fields)


def _account_from(grant: TokenGrant, login: str, now: float) -> GitHubAccount:
    expires_at = now + grant.expires_in if grant.expires_in else None
    return GitHubAccount(
        token=grant.access_token, login=login, method=TokenMethod.OAUTH_DEVICE,
        expires_at=expires_at, refresh_token=grant.refresh_token, scope=grant.scope,
    )


def _poll_until_terminal(code: DeviceCode, *, status: DeviceFlowStatus, deps: FlowDeps) -> None:
    client = deps.client or GitHubOAuthClient()
    client_id = deps.client_id if deps.client_id is not None else github_client_id()
    sleep = deps.sleep or time.sleep
    now = deps.now or time.time
    store = deps.store or store_account
    interval = code.interval
    while True:
        sleep(interval)
        poll = client.poll_token(client_id, code.device_code)
        if poll.kind is PollKind.SLOW_DOWN:
            interval += SLOW_DOWN_EXTRA_S
            continue
        if poll.kind is PollKind.PENDING:
            continue
        if poll.kind in _TERMINAL:
            _finish(status, _TERMINAL[poll.kind], now, error=poll.description or None)
            return
        login = client.fetch_user(poll.grant.access_token).login
        store(_account_from(poll.grant, login, now()))
        clear_access_cache()
        if deps.on_signed_in is not None:
            deps.on_signed_in()
        _finish(status, DeviceFlowState.DONE, now, login=login, error=None)
        return


def run_device_flow_job(code: DeviceCode, *, status: DeviceFlowStatus, deps: FlowDeps) -> None:
    """Poll GitHub until the flow ends; every failure lands in *status*, never a stuck slot."""
    now = deps.now or time.time

    def attempt() -> None:
        try:
            _poll_until_terminal(code, status=status, deps=deps)
        except GitHubUnreachable:
            _finish(status, DeviceFlowState.ERROR, now, error=MESSAGE_GITHUB_UNREACHABLE)
        except GitHubRefused as exc:
            _finish(status, DeviceFlowState.ERROR, now, error=MESSAGE_GITHUB_REFUSED.format(status=exc.status))

    run_isolated(
        attempt, label="github-device-flow", log=SHARED_LOG,
        on_error=lambda _exc: _finish(status, DeviceFlowState.ERROR, now, error=MESSAGE_FLOW_UNEXPECTED),
    )


def start_device_flow(*, status: DeviceFlowStatus | None = None, deps: FlowDeps | None = None) -> StartResult:
    """Claim the slot, fetch a user code, and start polling in the background."""
    status = status or _default_status
    deps = deps or FlowDeps()
    client_id = deps.client_id if deps.client_id is not None else github_client_id()
    if not client_id:
        return StartResult.NOT_CONFIGURED
    if not status.claim_slot():
        return StartResult.ALREADY_RUNNING
    client = deps.client or GitHubOAuthClient()
    try:
        code = client.request_device_code(client_id, GITHUB_OAUTH_SCOPE)
    except (GitHubUnreachable, GitHubRefused) as exc:
        status.set(state=DeviceFlowState.IDLE)  # release the slot; nothing started
        return StartResult.REFUSED if isinstance(exc, GitHubRefused) else StartResult.UNREACHABLE
    except BaseException:
        status.set(state=DeviceFlowState.IDLE)  # never leave the slot stuck at AWAITING_USER
        raise
    status.set(
        user_code=code.user_code, verification_uri=code.verification_uri,
        expires_in=code.expires_in, interval=code.interval,
    )
    try:
        (deps.spawn or _spawn_daemon)(lambda: run_device_flow_job(code, status=status, deps=deps))
    except RuntimeError:
        _finish(status, DeviceFlowState.ERROR, deps.now or time.time, error=MESSAGE_START_FAILED)
        return StartResult.FAILED
    return StartResult.STARTED
