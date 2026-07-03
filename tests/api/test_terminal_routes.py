import json

import pytest
from flask import Flask

from quodeq.api.terminal_routes import register_terminal_routes


class _FakeManager:
    def __init__(self):
        self.killed = False; self._alive = False; self.ensured = None
    def ensure_session(self, *, cwd, cols, rows): self._alive = True; self.ensured = (cwd, cols, rows)
    def scrollback(self): return b"hi\n"
    def read(self, max_bytes=65536): return b""
    def write(self, data): pass
    def resize(self, cols, rows): pass
    def kill(self): self.killed = True; self._alive = False
    @property
    def alive(self): return self._alive


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config["QUODEQ_API_KEY"] = None
    app.config["QUODEQ_BIND_HOST"] = "127.0.0.1"
    register_terminal_routes(app, manager=_FakeManager())
    return app


def test_status_allowed_on_loopback(app):
    c = app.test_client()
    r = c.get("/api/terminal/status", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
    assert r.get_json()["enabled"] is True


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


def test_kill_ok_on_loopback(app):
    c = app.test_client()
    r = c.post("/api/terminal/kill", headers={"Origin": "http://localhost"}, base_url="http://localhost")
    assert r.status_code == 200
