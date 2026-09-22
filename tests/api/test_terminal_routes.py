"""Tests for the terminal HTTP routes: status, kill, session CRUD and control frames."""
import pytest
from flask import Flask

from quodeq.api.terminal_routes import _apply_control, register_terminal_routes
from quodeq.terminal.sessions import TerminalSessionRegistry


class _FakeManager:
    def __init__(self):
        self.killed = False; self._alive = False; self.ensured = None

    def ensure_session(self, *, cwd, cols, rows): self._alive = True; self.ensured = (cwd, cols, rows)
    def scrollback(self): return "hi\n"
    def read(self, max_bytes=65536): return ""
    def write(self, data): pass
    def resize(self, cols, rows): pass
    def kill(self): self.killed = True; self._alive = False
    @property
    def alive(self): return self._alive
    @property
    def pid(self): return None


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config["QUODEQ_API_KEY"] = None
    app.config["QUODEQ_BIND_HOST"] = "127.0.0.1"
    # Real registry, fake PTYs: the registry is cheap and its locking/naming
    # behavior is part of what the routes rely on.
    register_terminal_routes(app, registry=TerminalSessionRegistry(manager_factory=_FakeManager))
    return app


def test_status_allowed_on_loopback(app):
    c = app.test_client()
    r = c.get("/api/terminal/status", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
    body = r.get_json()
    assert body["enabled"] is True
    assert isinstance(body["shell"], str) and body["shell"]


def test_status_enabled_without_origin_header(app):
    # Regression: /status is a same-origin GET and browsers omit the Origin
    # header on those. It must report enabled (env gate only), NOT refuse with
    # "Missing Origin header" — that bug made the terminal appear broken on mac.
    c = app.test_client()
    r = c.get("/api/terminal/status", base_url="http://localhost")  # no Origin
    assert r.status_code == 200
    body = r.get_json()
    assert body["enabled"] is True and body["reason"] is None


def test_status_refused_with_api_key(app):
    app.config["QUODEQ_API_KEY"] = "secret"
    c = app.test_client()
    r = c.get("/api/terminal/status", base_url="http://localhost")
    body = r.get_json()
    assert body["enabled"] is False and body["reason"]


def test_kill_refused_when_gated(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"
    c = app.test_client()
    r = c.post("/api/terminal/kill", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 403


def test_kill_kills_all_sessions(app):
    registry = app.extensions["terminal_registry"]
    a = registry.create(); b = registry.create()
    c = app.test_client()
    r = c.post("/api/terminal/kill", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
    assert a.manager.killed and b.manager.killed
    assert registry.list() == []


# --- session CRUD routes ---

def test_sessions_list_without_origin_header(app):
    # Same-origin GET like /status: must NOT require an Origin header.
    c = app.test_client()
    r = c.get("/api/terminal/sessions", base_url="http://localhost")
    assert r.status_code == 200
    body = r.get_json()
    assert body["sessions"] == [] and body["max"] == TerminalSessionRegistry.MAX_SESSIONS


def test_session_create_and_list(app):
    c = app.test_client()
    r = c.post("/api/terminal/sessions", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 201
    created = r.get_json()
    assert created["id"] and "· 1" in created["name"]
    listed = c.get("/api/terminal/sessions", base_url="http://localhost").get_json()["sessions"]
    assert [s["id"] for s in listed] == [created["id"]]


def test_session_create_refused_past_cap(app):
    c = app.test_client()
    for _ in range(TerminalSessionRegistry.MAX_SESSIONS):
        assert c.post("/api/terminal/sessions", headers={"Origin": "http://localhost"},
                      base_url="http://localhost").status_code == 201
    r = c.post("/api/terminal/sessions", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 409


def test_session_kill_removes_only_that_session(app):
    registry = app.extensions["terminal_registry"]
    a = registry.create(); b = registry.create()
    c = app.test_client()
    r = c.post(f"/api/terminal/sessions/{a.id}/kill",
               headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
    assert a.manager.killed and not b.manager.killed
    assert [s["id"] for s in registry.list()] == [b.id]


def test_session_kill_unknown_is_404(app):
    c = app.test_client()
    r = c.post("/api/terminal/sessions/nope/kill",
               headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 404


class _ResizeRecorder:
    def __init__(self):
        self.calls = []

    def resize(self, cols, rows):
        self.calls.append((cols, rows))


def test_apply_control_valid_resize_calls_manager():
    mgr = _ResizeRecorder()
    _apply_control(mgr, '{"resize":{"cols":100,"rows":40}}')
    assert mgr.calls == [(100, 40)]


@pytest.mark.parametrize("payload", [
    "not json",
    "{}",
    '{"resize":{"cols":"x"}}',
    '{"resize":123}',
])
def test_apply_control_malformed_is_noop_and_never_raises(payload):
    mgr = _ResizeRecorder()
    _apply_control(mgr, payload)  # must not raise
    assert mgr.calls == []


@pytest.mark.parametrize("payload", [
    '{"resize":{"cols":999999,"rows":40}}',   # > 65535 (struct.pack H overflow)
    '{"resize":{"cols":-5,"rows":40}}',        # negative
    '{"resize":{"cols":80,"rows":9999999}}',   # rows out of range
])
def test_apply_control_clamps_out_of_range_resize(payload):
    mgr = _ResizeRecorder()
    _apply_control(mgr, payload)  # must not raise (clamped, not dropped)
    assert len(mgr.calls) == 1
    cols, rows = mgr.calls[0]
    assert 1 <= cols <= 65535
    assert 1 <= rows <= 65535
