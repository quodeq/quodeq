# tests/api/test_routes_github_access.py
"""Every /api/git/probe and /api/github/* response shape and code."""
from __future__ import annotations

import pytest
from flask import Flask

from quodeq.api.routes_github_access import RouteDeps, register_github_access_routes
from quodeq.config.ai_provider_errors import PlaintextKeyRefusedError
from quodeq.config.github_account import GitHubAccount, TokenMethod
from quodeq.services.github_access import AccessMethod, AccessResult
from quodeq.services.github_device_flow import DeviceFlowState, StartResult
from quodeq.services.github_gh_cli import GhStatus
from quodeq.services.github_oauth_client import GitHubRefused, GitHubUnreachable, TokenRejected, UserInfo
from quodeq.shared.git_errors import GitFailureKind

_ACCT = GitHubAccount("gho_a", "victor", TokenMethod.OAUTH_DEVICE, expires_at=123.0)


class _Client:
    def __init__(self, user=UserInfo("victor", ("repo",)), exc=None):
        self.user, self.exc = user, exc

    def fetch_user(self, token):
        if self.exc:
            raise self.exc
        return self.user


def _app(**overrides):
    state = {"stored": [], "deleted": 0, "flow": {"state": DeviceFlowState.IDLE, "user_code": None, "verification_uri": None, "expires_in": None, "interval": None, "login": None, "error": None, "finished_at": None}}
    deps = RouteDeps(
        resolve=lambda url: AccessResult(True, AccessMethod.AMBIENT, GitFailureKind.OK, "", "github.com", True, None),
        load_account=lambda: None,
        delete_account=lambda: state.__setitem__("deleted", state["deleted"] + 1),
        store_account=lambda acct: state["stored"].append(acct) or (True, True),
        gh=lambda: GhStatus(False, False),
        start_flow=lambda: StartResult.STARTED,
        flow_status=lambda: dict(state["flow"]),
        client=_Client(),
    )
    deps = RouteDeps(**{**deps.__dict__, **overrides})
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_github_access_routes(app, deps=deps)
    return app.test_client(), state


def test_probe_reachable():
    client, _ = _app()
    resp = client.post("/api/git/probe", json={"url": "https://github.com/o/r.git"})
    assert resp.status_code == 200
    assert resp.get_json() == {"reachable": True, "method": "ambient", "kind": "ok", "detail": "", "host": "github.com", "isGitHub": True, "cloneUrl": None}


def test_probe_not_reachable_carries_kind_and_detail():
    result = AccessResult(False, AccessMethod.NONE, GitFailureKind.NOT_FOUND, "remote: Repository not found.", "github.com", True, None)
    client, _ = _app(resolve=lambda url: result)
    body = client.post("/api/git/probe", json={"url": "https://github.com/o/r.git"}).get_json()
    assert body["reachable"] is False and body["kind"] == "not_found" and body["method"] == "none"


def test_probe_validation():
    client, _ = _app()
    assert client.post("/api/git/probe", json={}).get_json()["code"] == "URL_REQUIRED"
    resp = client.post("/api/git/probe", json={"url": "http://github.com/o/r.git"})
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_URL"
    resp = client.post("/api/git/probe", json={"url": "https://127.0.0.1/o/r.git"})
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_URL"


def test_account_states():
    client, _ = _app()
    assert client.get("/api/github/account").get_json() == {"signedIn": False, "login": None, "method": "none", "expiresAt": None, "ghAvailable": False, "ghLoggedIn": False}
    client, _ = _app(gh=lambda: GhStatus(True, True, "gho_gh"))
    body = client.get("/api/github/account").get_json()
    assert body["method"] == "gh" and body["ghLoggedIn"] is True and body["signedIn"] is False
    client, _ = _app(load_account=lambda: _ACCT, gh=lambda: GhStatus(True, True, "gho_gh"))
    body = client.get("/api/github/account").get_json()
    assert body == {"signedIn": True, "login": "victor", "method": "quodeq", "expiresAt": 123.0, "ghAvailable": True, "ghLoggedIn": True}


@pytest.mark.parametrize("result,status,code", [
    (StartResult.NOT_CONFIGURED, 503, "GITHUB_NOT_CONFIGURED"),
    (StartResult.UNREACHABLE, 503, "OFFLINE"),
    (StartResult.FAILED, 500, "FLOW_START_FAILED"),
    (StartResult.REFUSED, 502, "GITHUB_REFUSED"),
])
def test_device_flow_start_failures(result, status, code):
    client, _ = _app(start_flow=lambda: result)
    resp = client.post("/api/github/device-flow")
    assert resp.status_code == status and resp.get_json()["code"] == code


def test_device_flow_start_and_status():
    awaiting = {"state": DeviceFlowState.AWAITING_USER, "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device", "expires_in": 900, "interval": 5, "login": None, "error": None, "finished_at": None}
    client, _ = _app(flow_status=lambda: dict(awaiting))
    resp = client.post("/api/github/device-flow")
    assert resp.status_code == 202
    assert resp.get_json() == {"userCode": "ABCD-1234", "verificationUri": "https://github.com/login/device", "expiresIn": 900, "interval": 5}
    client, _ = _app(start_flow=lambda: StartResult.ALREADY_RUNNING, flow_status=lambda: dict(awaiting))
    assert client.post("/api/github/device-flow").status_code == 200
    resp = client.get("/api/github/device-flow")
    assert resp.get_json() == {"state": "awaiting_user", "login": None, "error": None, "code": None, "userCode": "ABCD-1234", "verificationUri": "https://github.com/login/device"}


def test_device_flow_status_when_idle_is_409():
    client, _ = _app()
    resp = client.get("/api/github/device-flow")
    assert resp.status_code == 409 and resp.get_json()["code"] == "NO_FLOW"


def test_paste_token_stores_and_returns_login():
    client, state = _app()
    resp = client.post("/api/github/token", json={"token": "ghp_x"})
    assert resp.status_code == 200 and resp.get_json() == {"login": "victor"}
    acct = state["stored"][0]
    assert (acct.token, acct.login, acct.method, acct.scope) == ("ghp_x", "victor", TokenMethod.PASTED, "repo")


def test_paste_fine_grained_token_without_scopes_header_is_accepted():
    client, state = _app(client=_Client(user=UserInfo("victor", None)))
    assert client.post("/api/github/token", json={"token": "github_pat_x"}).status_code == 200
    assert state["stored"][0].scope == ""


def test_paste_token_errors():
    client, _ = _app()
    assert client.post("/api/github/token", json={}).get_json()["code"] == "TOKEN_REQUIRED"
    client, _ = _app(client=_Client(exc=TokenRejected("401")))
    resp = client.post("/api/github/token", json={"token": "bad"})
    assert resp.status_code == 400 and resp.get_json()["code"] == "TOKEN_INVALID"
    client, _ = _app(client=_Client(user=UserInfo("v", ("read:user",))))
    resp = client.post("/api/github/token", json={"token": "narrow"})
    assert resp.status_code == 400 and resp.get_json()["code"] == "TOKEN_SCOPE"
    client, _ = _app(client=_Client(exc=GitHubUnreachable("dns")))
    resp = client.post("/api/github/token", json={"token": "t"})
    assert resp.status_code == 503 and resp.get_json()["code"] == "OFFLINE"
    client, _ = _app(client=_Client(exc=GitHubRefused(403)))
    resp = client.post("/api/github/token", json={"token": "t"})
    assert resp.status_code == 502 and resp.get_json()["code"] == "GITHUB_REFUSED"


def test_paste_token_without_keyring_reports_env_var():
    def refuse(acct):
        raise PlaintextKeyRefusedError("GITHUB_ACCOUNT_API_KEY")
    client, _ = _app(store_account=refuse)
    resp = client.post("/api/github/token", json={"token": "t"})
    assert resp.status_code == 500
    assert resp.get_json()["code"] == "KEYRING_UNAVAILABLE" and resp.get_json()["envVar"] == "GITHUB_ACCOUNT_API_KEY"


def test_sign_out():
    client, state = _app(load_account=lambda: _ACCT)
    assert client.delete("/api/github/account").status_code == 204
    assert state["deleted"] == 1
