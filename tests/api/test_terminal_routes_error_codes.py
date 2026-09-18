"""Error-code coverage for the embedded-terminal routes.

Task 2 of usability cycle 1 (findings 5892, 5893, 5894, 5895): the six
identical ``{"error": "forbidden"}`` sites, the session-limit 409, the
unknown-session 404, and the "paths must be a list" 400 all gain a
machine-readable ``code``. The ``app``/``_FakeManager`` fixtures come from
``tests/api/test_terminal_routes.py`` rather than being duplicated here.
"""
from __future__ import annotations

from quodeq.terminal.sessions import TerminalSessionRegistry
from tests.api.test_terminal_routes import _FakeManager, app  # noqa: F401 -- app is a pytest fixture

_ORIGIN = {"Origin": "http://localhost"}


# --- the six identical forbidden sites (5892) --------------------------------


def test_sessions_list_forbidden_has_code(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.get("/api/terminal/sessions", base_url="http://localhost")
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_session_create_forbidden_has_code(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/sessions", headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_session_kill_forbidden_has_code(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/sessions/some-id/kill", headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_kill_all_forbidden_has_code(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/kill", headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_resolve_forbidden_has_code(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/resolve", headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


def test_open_forbidden_has_code(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/open", headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 403
    assert r.get_json()["code"] == "FORBIDDEN"


# --- session limit (5893), unknown session (5894), bad input (5895) ----------


def test_session_create_refused_past_cap_has_session_limit_code(app):
    c = app.test_client()
    for _ in range(TerminalSessionRegistry.MAX_SESSIONS):
        assert c.post(
            "/api/terminal/sessions", headers=_ORIGIN, base_url="http://localhost"
        ).status_code == 201
    r = c.post("/api/terminal/sessions", headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 409
    assert r.get_json()["code"] == "SESSION_LIMIT"


def test_session_kill_unknown_has_code(app):
    c = app.test_client()
    r = c.post(
        "/api/terminal/sessions/nope/kill", headers=_ORIGIN, base_url="http://localhost"
    )
    assert r.status_code == 404
    assert r.get_json()["code"] == "UNKNOWN_SESSION"


def test_resolve_paths_not_list_has_invalid_input_code(app):
    c = app.test_client()
    r = c.post(
        "/api/terminal/resolve", json={"paths": "not-a-list"},
        headers=_ORIGIN, base_url="http://localhost",
    )
    assert r.status_code == 400
    assert r.get_json()["code"] == "INVALID_INPUT"
