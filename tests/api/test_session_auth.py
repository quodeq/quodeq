"""The local API refuses requests that do not come from the Quodeq UI.

An analysis agent runs on the same machine as the API and can reach it on
loopback with curl, which ignores the Origin check. Every ``/api`` route but
the explicit allowlist must therefore answer 401 to a request without this
launch's session secret, whatever its method.
"""
from __future__ import annotations

import re

import pytest

from quodeq.api.session_auth import CODE_SESSION_REQUIRED, OPEN_PATHS
from quodeq.api.app import create_app
from quodeq.shared.api_session import SESSION_HEADER, WEBVIEW_TOKEN_UA_PREFIX
from tests._session_client import unauthenticated_client

_SECRET = "pinned-session-secret"  # noqa: S105 - test fixture, not a credential
_LOCAL = {"REMOTE_ADDR": "127.0.0.1"}
_CONVERTER = re.compile(r"<(?:[a-z]+:)?[a-z_]+>")


@pytest.fixture(autouse=True)
def _generous_rate_limit(monkeypatch):
    # Failed auth counts toward the rate limit; the route walk fails hundreds of times on purpose.
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "100000")


def _app(**kwargs):
    return create_app(test_config={"QUODEQ_SESSION_SECRET": _SECRET}, **kwargs)


@pytest.fixture
def app():
    return _app()


def _api_routes(app) -> list[tuple[str, str]]:
    routes = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or rule.rule in OPEN_PATHS:
            continue
        url = _CONVERTER.sub("x", rule.rule)
        routes += [(m, url) for m in sorted(rule.methods - {"HEAD", "OPTIONS"})]
    return routes


def test_every_api_route_but_the_allowlist_refuses_a_request_without_the_session(app):
    routes = _api_routes(app)
    assert len(routes) > 100, "the route walk must see the real app"
    client = unauthenticated_client(app)
    open_routes = []
    for method, url in routes:
        resp = client.open(url, method=method, environ_base=_LOCAL, headers={"Origin": "http://localhost"})
        if resp.status_code != 401 or resp.get_json()["code"] != CODE_SESSION_REQUIRED:
            open_routes.append(f"{method} {url} -> {resp.status_code}")
    assert open_routes == []


def test_the_allowlist_is_only_health_and_the_launch_link():
    assert OPEN_PATHS == {"/api/health", "/api/session/open"}


def test_health_answers_without_a_session(app):
    assert unauthenticated_client(app).get("/api/health", environ_base=_LOCAL).status_code == 200


@pytest.mark.parametrize("credential", [
    {"headers": {SESSION_HEADER: _SECRET}},
    {"headers": {"User-Agent": f"QuodeqDesktop/1.0 {WEBVIEW_TOKEN_UA_PREFIX}{_SECRET} Safari"}},
])
def test_the_header_and_the_desktop_window_ua_carry_the_session(app, credential):
    resp = unauthenticated_client(app).get("/api/evaluations", environ_base=_LOCAL, **credential)
    assert resp.status_code == 200


@pytest.mark.parametrize("wrong", ["not-it", "pinned-session-secrex", "sécret", ""])
def test_a_wrong_secret_is_refused_everywhere_it_can_be_sent(app, wrong):
    client = unauthenticated_client(app)
    client.set_cookie(app.extensions["session_auth"].cookie_name, wrong)
    resp = client.get("/api/evaluations", environ_base=_LOCAL, headers={
        SESSION_HEADER: wrong, "User-Agent": f"QuodeqDesktop/1.0 {WEBVIEW_TOKEN_UA_PREFIX}{wrong}",
    })
    assert resp.status_code == 401


def test_a_launch_code_sets_the_cookie_once(app):
    issuer = unauthenticated_client(app)
    link = issuer.post("/api/session/code", environ_base=_LOCAL, headers={SESSION_HEADER: _SECRET}).get_json()["path"]

    browser = unauthenticated_client(app)
    opened = browser.get(link, environ_base=_LOCAL)
    assert opened.status_code == 302 and opened.headers["Location"] == "/"
    cookie = opened.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert browser.get("/api/evaluations", environ_base=_LOCAL).status_code == 200

    replay = unauthenticated_client(app).get(link, environ_base=_LOCAL)
    assert replay.status_code == 401 and "Set-Cookie" not in replay.headers


def test_an_expired_launch_code_is_refused(app, monkeypatch):
    from quodeq.api import session_auth
    code = app.extensions["session_auth"].issue_code()
    later = session_auth.time.monotonic() + session_auth._CODE_TTL_S + 1
    monkeypatch.setattr(session_auth.time, "monotonic", lambda: later)
    resp = unauthenticated_client(app).get(f"/api/session/open?code={code}", environ_base=_LOCAL)
    assert resp.status_code == 401


def test_the_session_header_stands_in_for_the_origin_but_the_cookie_does_not(app):
    """The header cannot come from a cross-site page; a cookie rides along on one."""
    header = unauthenticated_client(app).post(
        "/api/session/code", environ_base=_LOCAL, headers={SESSION_HEADER: _SECRET})
    assert header.status_code == 200
    cookie_only = unauthenticated_client(app)
    cookie_only.set_cookie(app.extensions["session_auth"].cookie_name, _SECRET)
    assert cookie_only.post("/api/session/code", environ_base=_LOCAL).status_code == 403


def test_the_app_page_explains_how_to_get_in_and_assets_stay_public(tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "app.js").write_text("console.log(1)")
    app = _app(static_dist=str(tmp_path))
    client = unauthenticated_client(app)
    page = client.get("/", environ_base=_LOCAL)
    assert page.status_code == 401 and b"quodeq dashboard" in page.data and b"id=root" not in page.data
    assert client.get("/projects/demo", environ_base=_LOCAL).status_code == 401
    assert client.get("/app.js", environ_base=_LOCAL).status_code == 200


def test_remote_mode_keeps_its_bearer_check_and_skips_the_session():
    app = create_app(api_key="remote-key")
    client = unauthenticated_client(app)
    remote = {"REMOTE_ADDR": "10.0.0.5"}
    assert client.get("/api/evaluations", environ_base=remote).status_code == 401
    ok = client.get("/api/evaluations", environ_base=remote, headers={"Authorization": "Bearer remote-key"})
    assert ok.status_code == 200


def test_each_app_mints_its_own_secret():
    assert create_app().extensions["session_auth"].secret != create_app().extensions["session_auth"].secret
