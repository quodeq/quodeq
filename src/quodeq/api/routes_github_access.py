# src/quodeq/api/routes_github_access.py
"""/api/git/probe and /api/github/*: the access ladder and GitHub sign-in.

The probe is host-agnostic (any https/ssh remote); the github routes manage
the one stored quodeq token, the device-flow job and the paste path. Every
collaborator comes through RouteDeps so tests run the real Flask routes
against fakes without monkeypatching module globals.
"""
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable

from flask import Flask, Response, jsonify

from quodeq.api._constants import CODE_INVALID_INPUT, CODE_KEYRING_UNAVAILABLE
from quodeq.api.helpers import json_error, optional_json_object_or_response
from quodeq.config.ai_provider_errors import PLAINTEXT_KEY_REFUSED_MESSAGE, PlaintextKeyRefusedError
from quodeq.config.github_account import GitHubAccount, TokenMethod, delete_account, load_account, store_account
from quodeq.config.github_app import GITHUB_OAUTH_SCOPE
from quodeq.services.github_access import AccessResult, clear_access_cache, resolve_access
from quodeq.services.github_device_flow import (
    DeviceFlowState, FlowDeps, StartResult, get_device_flow_status, start_device_flow,
)
from quodeq.services.github_gh_cli import GhStatus, gh_status
from quodeq.services.github_oauth_client import GitHubOAuthClient, GitHubRefused, GitHubUnreachable, TokenRejected
from quodeq.services.shared_repo import validate_remote_url
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.repo import is_repo_url

CODE_ACCESS_PREFIX = "ACCESS_"
CODE_URL_REQUIRED = "URL_REQUIRED"
CODE_INVALID_URL = "INVALID_URL"
CODE_GITHUB_NOT_CONFIGURED = "GITHUB_NOT_CONFIGURED"
CODE_OFFLINE = "OFFLINE"
CODE_FLOW_START_FAILED = "FLOW_START_FAILED"
CODE_NO_FLOW = "NO_FLOW"
CODE_TOKEN_REQUIRED = "TOKEN_REQUIRED"
CODE_TOKEN_INVALID = "TOKEN_INVALID"
CODE_TOKEN_SCOPE = "TOKEN_SCOPE"
CODE_GITHUB_REFUSED = "GITHUB_REFUSED"
CODE_FLOW_FAILED = "FLOW_FAILED"

ACCOUNT_METHOD_QUODEQ = "quodeq"
ACCOUNT_METHOD_GH = "gh"
ACCOUNT_METHOD_NONE = "none"

_START_FAILURES = {
    StartResult.NOT_CONFIGURED: ("GitHub sign-in is not configured in this build.", HTTPStatus.SERVICE_UNAVAILABLE, CODE_GITHUB_NOT_CONFIGURED),
    StartResult.UNREACHABLE: ("GitHub could not be reached.", HTTPStatus.SERVICE_UNAVAILABLE, CODE_OFFLINE),
    StartResult.REFUSED: ("GitHub refused the device-code request. Check the OAuth client id.", HTTPStatus.BAD_GATEWAY, CODE_GITHUB_REFUSED),
    StartResult.FAILED: ("could not start the sign-in job, see server logs", HTTPStatus.INTERNAL_SERVER_ERROR, CODE_FLOW_START_FAILED),
}


def _start_flow() -> StartResult:
    """Start the device flow with production logging wired in."""
    return start_device_flow(deps=FlowDeps(log=SHARED_LOG))


def access_failure_response(result: AccessResult) -> tuple[Response, int]:
    """400 body for a URL the ladder could not reach: the kind as a code suffix
    plus the fields the UI's access panel renders from."""
    body = {
        "error": f"could not reach {result.host}: {result.kind}",
        "code": f"{CODE_ACCESS_PREFIX}{result.kind.upper()}",
        "kind": result.kind, "detail": result.detail, "host": result.host, "isGitHub": result.is_github,
    }
    return jsonify(body), HTTPStatus.BAD_REQUEST


@dataclass(frozen=True)
class RouteDeps:
    """Every collaborator the routes call, injectable for tests."""

    resolve: Callable[[str], AccessResult] = resolve_access
    load_account: Callable[[], GitHubAccount | None] = load_account
    delete_account: Callable[[], None] = delete_account
    store_account: Callable[[GitHubAccount], tuple[bool, bool]] = store_account
    gh: Callable[[], GhStatus] = gh_status
    start_flow: Callable[[], StartResult] = _start_flow
    flow_status: Callable[[], dict] = get_device_flow_status
    client: GitHubOAuthClient | None = None  # None: a real client, built per call


def _probe(deps: RouteDeps) -> Response | tuple[Response, int]:
    body = optional_json_object_or_response(CODE_INVALID_INPUT)
    if not isinstance(body, dict):
        return body
    url = str(body.get("url") or "").strip()
    if not url:
        return json_error("url is required", HTTPStatus.BAD_REQUEST, CODE_URL_REQUIRED)
    try:
        if not is_repo_url(url):
            return json_error("not a recognised remote repository URL", HTTPStatus.BAD_REQUEST, CODE_INVALID_URL)
        validate_remote_url(url)
    except ValueError:
        return json_error("use an https or ssh URL to a public host", HTTPStatus.BAD_REQUEST, CODE_INVALID_URL)
    r = deps.resolve(url)
    return jsonify({
        "reachable": r.reachable, "method": r.method, "kind": r.kind, "detail": r.detail,
        "host": r.host, "isGitHub": r.is_github, "cloneUrl": r.clone_url,
    })


def _account(deps: RouteDeps) -> Response:
    account = deps.load_account()
    gh = deps.gh()
    method = ACCOUNT_METHOD_QUODEQ if account else ACCOUNT_METHOD_GH if gh.logged_in else ACCOUNT_METHOD_NONE
    return jsonify({
        "signedIn": account is not None, "login": account.login if account else None, "method": method,
        "expiresAt": account.expires_at if account else None,
        "ghAvailable": gh.available, "ghLoggedIn": gh.logged_in,
    })


def _flow_snapshot(deps: RouteDeps) -> dict:
    snap = deps.flow_status()
    return {"userCode": snap["user_code"], "verificationUri": snap["verification_uri"], "expiresIn": snap["expires_in"], "interval": snap["interval"]}


def _device_flow_start(deps: RouteDeps) -> Response | tuple[Response, int]:
    result = deps.start_flow()
    if result in _START_FAILURES:
        message, status, code = _START_FAILURES[result]
        return json_error(message, status, code)
    status = HTTPStatus.OK if result == StartResult.ALREADY_RUNNING else HTTPStatus.ACCEPTED
    return jsonify(_flow_snapshot(deps)), status


def _device_flow_status(deps: RouteDeps) -> Response | tuple[Response, int]:
    snap = deps.flow_status()
    if snap["state"] == DeviceFlowState.IDLE:
        return json_error("no sign-in in progress", HTTPStatus.CONFLICT, CODE_NO_FLOW)
    return jsonify({
        "state": snap["state"], "login": snap["login"], "error": snap["error"],
        "code": None if snap["error"] is None else CODE_FLOW_FAILED,
        "userCode": snap["user_code"], "verificationUri": snap["verification_uri"],
    })


def _paste_token(deps: RouteDeps) -> Response | tuple[Response, int]:
    body = optional_json_object_or_response(CODE_INVALID_INPUT)
    if not isinstance(body, dict):
        return body
    token = str(body.get("token") or "").strip()
    if not token:
        return json_error("token is required", HTTPStatus.BAD_REQUEST, CODE_TOKEN_REQUIRED)
    client = deps.client or GitHubOAuthClient()
    try:
        user = client.fetch_user(token)
    except TokenRejected:
        return json_error("GitHub rejected this token.", HTTPStatus.BAD_REQUEST, CODE_TOKEN_INVALID)
    except GitHubUnreachable:
        return json_error("GitHub could not be reached.", HTTPStatus.SERVICE_UNAVAILABLE, CODE_OFFLINE)
    except GitHubRefused as exc:
        return json_error(f"GitHub refused the request (HTTP {exc.status}).", HTTPStatus.BAD_GATEWAY, CODE_GITHUB_REFUSED)
    if user.scopes is not None and GITHUB_OAUTH_SCOPE not in user.scopes:
        return json_error("This token lacks the repo scope.", HTTPStatus.BAD_REQUEST, CODE_TOKEN_SCOPE)
    scope = GITHUB_OAUTH_SCOPE if user.scopes is not None else ""
    account = GitHubAccount(token=token, login=user.login, method=TokenMethod.PASTED, scope=scope)
    try:
        deps.store_account(account)
    except PlaintextKeyRefusedError as exc:
        return jsonify({"error": PLAINTEXT_KEY_REFUSED_MESSAGE.format(env_var=exc.env_var), "code": CODE_KEYRING_UNAVAILABLE, "envVar": exc.env_var}), HTTPStatus.INTERNAL_SERVER_ERROR
    clear_access_cache()
    return jsonify({"login": user.login})


def _sign_out(deps: RouteDeps) -> tuple[str, int]:
    deps.delete_account()
    clear_access_cache()
    return "", HTTPStatus.NO_CONTENT


def register_github_access_routes(app: Flask, deps: RouteDeps | None = None) -> None:
    """Bind the probe and the GitHub account routes."""
    d = deps or RouteDeps()
    app.post("/api/git/probe", endpoint="git_probe")(lambda: _probe(d))
    app.get("/api/github/account", endpoint="github_account")(lambda: _account(d))
    app.post("/api/github/device-flow", endpoint="github_device_flow_start")(lambda: _device_flow_start(d))
    app.get("/api/github/device-flow", endpoint="github_device_flow_status")(lambda: _device_flow_status(d))
    app.post("/api/github/token", endpoint="github_token")(lambda: _paste_token(d))
    app.delete("/api/github/account", endpoint="github_sign_out")(lambda: _sign_out(d))
