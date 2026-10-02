"""Device-flow job state machine (inline spawn, fake clock, no network)."""
from __future__ import annotations

from quodeq.config.ai_provider_errors import PLAINTEXT_KEY_REFUSED_MESSAGE, PlaintextKeyRefusedError
from quodeq.config.github_account import TokenMethod
from quodeq.services.github_device_flow import (
    SLOW_DOWN_EXTRA_S, DeviceFlowState, DeviceFlowStatus, FlowDeps, StartResult, get_device_flow_status,
    start_device_flow,
)
from quodeq.services.github_oauth_client import (
    DeviceCode, GitHubRefused, GitHubUnreachable, PollKind, TokenGrant, TokenPoll, UserInfo,
)

_CODE = DeviceCode("dev", "ABCD-1234", "https://github.com/login/device", expires_in=900, interval=5)
_GRANT = TokenGrant("gho_a", "repo", None, None)


class _Client:
    def __init__(self, polls, *, code=_CODE, user=UserInfo("victor", ("repo",)), code_exc=None):
        self.polls, self.code, self.user, self.code_exc = list(polls), code, user, code_exc

    def request_device_code(self, client_id, scope):
        if self.code_exc:
            raise self.code_exc
        return self.code

    def poll_token(self, client_id, device_code):
        return self.polls.pop(0)

    def fetch_user(self, token):
        return self.user


def _deps(client, stored=None, sleeps=None, on_signed_in=None):
    stored = [] if stored is None else stored
    sleeps = [] if sleeps is None else sleeps
    return FlowDeps(
        client=client, client_id="Iv1.x", store=lambda acct: stored.append(acct) or (True, True),
        spawn=lambda fn: fn(), sleep=sleeps.append, now=lambda: 1000.0, on_signed_in=on_signed_in,
    )


def test_not_configured_when_client_id_is_empty():
    status = DeviceFlowStatus()
    deps = FlowDeps(client=_Client([]), client_id="", spawn=lambda fn: fn())
    assert start_device_flow(status=status, deps=deps) is StartResult.NOT_CONFIGURED
    assert get_device_flow_status(status)["state"] == DeviceFlowState.IDLE


def test_unreachable_when_device_code_request_fails():
    status = DeviceFlowStatus()
    deps = _deps(_Client([], code_exc=GitHubUnreachable("dns")))
    assert start_device_flow(status=status, deps=deps) is StartResult.UNREACHABLE
    assert get_device_flow_status(status)["state"] == DeviceFlowState.IDLE


def test_refused_when_device_code_request_is_answered_4xx():
    status = DeviceFlowStatus()
    deps = _deps(_Client([], code_exc=GitHubRefused(401)))
    assert start_device_flow(status=status, deps=deps) is StartResult.REFUSED
    assert get_device_flow_status(status)["state"] == DeviceFlowState.IDLE


def test_granted_stores_the_account_and_reports_done():
    status, stored, signed = DeviceFlowStatus(), [], []
    polls = [TokenPoll(PollKind.PENDING), TokenPoll(PollKind.GRANTED, _GRANT)]
    deps = _deps(_Client(polls), stored=stored, on_signed_in=lambda: signed.append(True))
    assert start_device_flow(status=status, deps=deps) is StartResult.STARTED
    snap = get_device_flow_status(status)
    assert snap["state"] == DeviceFlowState.DONE and snap["login"] == "victor"
    assert snap["user_code"] == "ABCD-1234" and snap["verification_uri"] == _CODE.verification_uri
    acct = stored[0]
    assert (acct.token, acct.login, acct.method, acct.expires_at, acct.scope) == ("gho_a", "victor", TokenMethod.OAUTH_DEVICE, None, "repo")
    assert signed == [True]


def test_expiring_grant_records_expiry_and_refresh_token():
    status, stored = DeviceFlowStatus(), []
    grant = TokenGrant("ghu_a", "repo", 28800, "ghr_b")
    start_device_flow(status=status, deps=_deps(_Client([TokenPoll(PollKind.GRANTED, grant)]), stored=stored))
    assert stored[0].expires_at == 1000.0 + 28800 and stored[0].refresh_token == "ghr_b"


def test_slow_down_grows_the_interval_and_keeps_polling():
    status, sleeps = DeviceFlowStatus(), []
    polls = [TokenPoll(PollKind.SLOW_DOWN), TokenPoll(PollKind.PENDING), TokenPoll(PollKind.GRANTED, _GRANT)]
    start_device_flow(status=status, deps=_deps(_Client(polls), sleeps=sleeps))
    assert sleeps == [5, 5 + SLOW_DOWN_EXTRA_S, 5 + SLOW_DOWN_EXTRA_S]
    assert get_device_flow_status(status)["state"] == DeviceFlowState.DONE


def test_expired_and_denied_are_terminal_states():
    for kind, state in ((PollKind.EXPIRED, DeviceFlowState.EXPIRED), (PollKind.DENIED, DeviceFlowState.DENIED)):
        status = DeviceFlowStatus()
        start_device_flow(status=status, deps=_deps(_Client([TokenPoll(kind, description="x")])))
        snap = get_device_flow_status(status)
        assert snap["state"] == state and snap["finished_at"] is not None


def test_failed_poll_and_unreachable_mid_flow_are_errors():
    status = DeviceFlowStatus()
    start_device_flow(status=status, deps=_deps(_Client([TokenPoll(PollKind.FAILED, description="bad code")])))
    assert get_device_flow_status(status)["state"] == DeviceFlowState.ERROR
    assert get_device_flow_status(status)["error"] == "bad code"

    class Boom(_Client):
        def poll_token(self, *_):
            raise GitHubUnreachable("offline")
    status = DeviceFlowStatus()
    start_device_flow(status=status, deps=_deps(Boom([])))
    assert get_device_flow_status(status)["state"] == DeviceFlowState.ERROR


def test_refused_poll_is_an_error_naming_the_http_status():
    class Refusing(_Client):
        def poll_token(self, *_):
            raise GitHubRefused(403)
    status = DeviceFlowStatus()
    start_device_flow(status=status, deps=_deps(Refusing([])))
    snap = get_device_flow_status(status)
    assert snap["state"] == DeviceFlowState.ERROR and "HTTP 403" in snap["error"]


def test_second_start_while_awaiting_is_already_running():
    status = DeviceFlowStatus()
    deps = _deps(_Client([TokenPoll(PollKind.GRANTED, _GRANT)]))
    deps_noop_spawn = FlowDeps(**{**deps.__dict__, "spawn": lambda fn: None})  # claim, never run
    assert start_device_flow(status=status, deps=deps_noop_spawn) is StartResult.STARTED
    assert start_device_flow(status=status, deps=deps_noop_spawn) is StartResult.ALREADY_RUNNING


def test_missing_keychain_finishes_error_with_the_keyring_message_and_code():
    status = DeviceFlowStatus()

    def refuse(acct):
        raise PlaintextKeyRefusedError("GITHUB_ACCOUNT_API_KEY")

    deps = FlowDeps(
        client=_Client([TokenPoll(PollKind.GRANTED, _GRANT)]), client_id="Iv1.x", store=refuse,
        spawn=lambda fn: fn(), sleep=lambda s: None, now=lambda: 1000.0,
    )
    start_device_flow(status=status, deps=deps)
    snap = get_device_flow_status(status)
    assert snap["state"] == DeviceFlowState.ERROR
    assert snap["error"] == PLAINTEXT_KEY_REFUSED_MESSAGE.format(env_var="GITHUB_ACCOUNT_API_KEY")
    assert snap["code"] == "KEYRING_UNAVAILABLE"
