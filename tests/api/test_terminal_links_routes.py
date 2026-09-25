"""Tests for the /api/terminal/resolve and /open routes (editor launching)."""
from __future__ import annotations

import pytest
from flask import Flask

from quodeq.api.terminal_routes import register_terminal_routes
from quodeq.terminal.sessions import TerminalSessionRegistry
from quodeq.terminal.links import Editor


# --- routes -----------------------------------------------------------------

class _FakeManager:
    def __init__(self, pid=4321):
        self.pid = pid
        self._alive = False

    def ensure_session(self, *, cwd, cols, rows):
        self._alive = True

    def scrollback(self):
        return ""

    def read(self, max_bytes=65536):
        return ""

    def write(self, data):
        pass

    def resize(self, cols, rows):
        pass

    def kill(self):
        self._alive = False

    @property
    def alive(self):
        return self._alive


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config["QUODEQ_API_KEY"] = None
    app.config["QUODEQ_BIND_HOST"] = "127.0.0.1"
    registry = TerminalSessionRegistry(manager_factory=_FakeManager)
    # /resolve and /open with no explicit session fall back to the first LIVE
    # session's pid — mirror the old always-present manager.
    registry.create().manager._alive = True
    register_terminal_routes(app, registry=registry)
    return app


_H = {"Origin": "http://localhost"}


def test_resolve_route_reports_existence(app, monkeypatch):
    monkeypatch.setattr("quodeq.api.terminal_routes.resolve_bases", lambda pid: ["/base"])
    monkeypatch.setattr(
        "quodeq.api.terminal_routes.resolve_path",
        lambda token, bases: (f"/base/{token}", token == "real.py"),
    )
    c = app.test_client()
    r = c.post("/api/terminal/resolve", json={"paths": ["real.py", "ghost.py"]},
               headers=_H, base_url="http://localhost")
    assert r.status_code == 200
    resolved = r.get_json()["resolved"]
    assert resolved == [
        {"input": "real.py", "abs": "/base/real.py", "exists": True},
        {"input": "ghost.py", "abs": "/base/ghost.py", "exists": False},
    ]


def test_resolve_route_rejects_non_list(app):
    c = app.test_client()
    r = c.post("/api/terminal/resolve", json={"paths": "x"}, headers=_H, base_url="http://localhost")
    assert r.status_code == 400


def test_resolve_route_gated(app):
    app.config["QUODEQ_BIND_HOST"] = "0.0.0.0"  # forces gate refusal
    c = app.test_client()
    r = c.post("/api/terminal/resolve", json={"paths": []}, headers=_H, base_url="http://localhost")
    assert r.status_code == 403


def test_open_route_launches_editor(app, monkeypatch):
    calls = {}
    # Bypass containment/realpath so the test is deterministic; safe path == input.
    monkeypatch.setattr("quodeq.api.terminal_routes.resolve_bases", lambda pid: ["/base"])
    monkeypatch.setattr("quodeq.api.terminal_routes.safe_editor_path", lambda p, bases: p)
    monkeypatch.setattr("quodeq.api.terminal_routes.os.path.isfile", lambda p: True)
    monkeypatch.setattr("quodeq.api.terminal_routes.detect_editor",
                        lambda: Editor("code", "/usr/bin/code", True))

    def _popen(argv, **kw):
        calls["argv"] = argv
        calls["kw"] = kw
        return object()

    monkeypatch.setattr("quodeq.terminal.links.subprocess.Popen", _popen)
    c = app.test_client()
    r = c.post("/api/terminal/open", json={"path": "/proj/a.py", "line": 9, "col": 2},
               headers=_H, base_url="http://localhost")
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"opened": True, "editor": "code"}
    assert calls["argv"] == ["/usr/bin/code", "-g", "/proj/a.py:9:2"]
    assert calls["kw"].get("start_new_session") is True


def test_open_route_rejects_path_outside_bases(app, monkeypatch):
    # safe_editor_path returns None for anything outside the terminal's dirs.
    monkeypatch.setattr("quodeq.api.terminal_routes.resolve_bases", lambda pid: ["/base"])
    monkeypatch.setattr("quodeq.api.terminal_routes.safe_editor_path", lambda p, bases: None)
    launched = []
    monkeypatch.setattr("quodeq.terminal.links.subprocess.Popen",
                        lambda *a, **k: launched.append(a))
    c = app.test_client()
    r = c.post("/api/terminal/open", json={"path": "/etc/passwd"}, headers=_H, base_url="http://localhost")
    assert r.get_json() == {"opened": False, "editor": None}
    assert launched == []


def test_open_route_missing_file_not_opened(app, monkeypatch):
    monkeypatch.setattr("quodeq.api.terminal_routes.resolve_bases", lambda pid: ["/base"])
    monkeypatch.setattr("quodeq.api.terminal_routes.safe_editor_path", lambda p, bases: p)
    monkeypatch.setattr("quodeq.api.terminal_routes.os.path.isfile", lambda p: False)
    launched = []
    monkeypatch.setattr("quodeq.terminal.links.subprocess.Popen",
                        lambda *a, **k: launched.append(a))
    c = app.test_client()
    r = c.post("/api/terminal/open", json={"path": "/gone.py"}, headers=_H, base_url="http://localhost")
    assert r.get_json() == {"opened": False, "editor": None}
    assert launched == []


def test_open_route_fail_soft_on_launch_error(app, monkeypatch):
    monkeypatch.setattr("quodeq.api.terminal_routes.resolve_bases", lambda pid: ["/base"])
    monkeypatch.setattr("quodeq.api.terminal_routes.safe_editor_path", lambda p, bases: p)
    monkeypatch.setattr("quodeq.api.terminal_routes.os.path.isfile", lambda p: True)
    monkeypatch.setattr("quodeq.api.terminal_routes.detect_editor",
                        lambda: Editor("code", "/usr/bin/code", True))

    def _boom(*a, **k):
        raise OSError("no exec")

    monkeypatch.setattr("quodeq.terminal.links.subprocess.Popen", _boom)
    c = app.test_client()
    r = c.post("/api/terminal/open", json={"path": "/proj/a.py"}, headers=_H, base_url="http://localhost")
    assert r.status_code == 200
    assert r.get_json() == {"opened": False, "editor": "code"}


def test_open_route_requires_path(app):
    c = app.test_client()
    r = c.post("/api/terminal/open", json={}, headers=_H, base_url="http://localhost")
    assert r.status_code == 400
