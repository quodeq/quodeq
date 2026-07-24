"""Tests for clickable-terminal-link resolution and editor launching.

Covers the pure helpers in quodeq.terminal.links (no real filesystem, PATH, or
subprocess) and the /api/terminal/resolve + /open routes.
"""
from __future__ import annotations

import os

import pytest
from flask import Flask

from quodeq.api.terminal_routes import register_terminal_routes
from quodeq.terminal.links import (
    Editor,
    build_open_argv,
    child_cwd,
    detect_editor,
    resolve_path,
    safe_editor_path,
)


# --- resolve_path -----------------------------------------------------------

def test_resolve_absolute_existing():
    abs_path, exists = resolve_path(
        "/proj/a.py", ["/base"], isfile=lambda p: p == "/proj/a.py",
    )
    assert abs_path == "/proj/a.py"
    assert exists is True


def test_resolve_absolute_missing():
    abs_path, exists = resolve_path("/nope.py", ["/base"], isfile=lambda p: False)
    assert abs_path == "/nope.py"
    assert exists is False


def test_resolve_relative_picks_first_existing_base():
    # Exists only under the second base.
    real = "/second/rel.py"
    abs_path, exists = resolve_path(
        "rel.py", ["/first", "/second"], isfile=lambda p: p == real,
    )
    assert abs_path == real
    assert exists is True


def test_resolve_relative_none_exist_falls_back_to_first_base():
    abs_path, exists = resolve_path(
        "rel.py", ["/first", "/second"], isfile=lambda p: False,
    )
    assert abs_path == "/first/rel.py"
    assert exists is False


# --- safe_editor_path -------------------------------------------------------

def test_safe_editor_path_within_base_returns_realpath():
    got = safe_editor_path("/home/u/proj/a.py", ["/home/u"], realpath=lambda p: p)
    assert got == "/home/u/proj/a.py"


def test_safe_editor_path_outside_bases_is_none():
    assert safe_editor_path("/etc/passwd", ["/home/u"], realpath=lambda p: p) is None


def test_safe_editor_path_symlink_escape_rejected():
    # realpath resolves the link OUT of the base -> rejected (not just lexical).
    def _rp(p):
        return "/etc/shadow" if p == "/home/u/link" else p

    assert safe_editor_path("/home/u/link", ["/home/u"], realpath=_rp) is None


def test_safe_editor_path_normalizes_returned_value():
    got = safe_editor_path(
        "/home/u/../u/proj/a.py", ["/home/u"], realpath=os.path.normpath,
    )
    assert got == "/home/u/proj/a.py"


def test_safe_editor_path_checks_multiple_bases():
    got = safe_editor_path("/second/a.py", ["/first", "/second"], realpath=lambda p: p)
    assert got == "/second/a.py"


# --- detect_editor ----------------------------------------------------------

def test_detect_editor_prefers_code_on_path():
    ed = detect_editor(which=lambda n: "/usr/bin/code" if n == "code" else None,
                       isfile=lambda p: False, platform="darwin")
    assert ed == Editor(name="code", path="/usr/bin/code", supports_line=True)


def test_detect_editor_finds_code_via_known_location_when_path_misses():
    # GUI-launched macOS app: `code` not on PATH, but the bundled CLI exists.
    bundled = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
    ed = detect_editor(which=lambda n: None, isfile=lambda p: p == bundled,
                       platform="darwin")
    assert ed.name == "code" and ed.path == bundled and ed.supports_line


def test_detect_editor_falls_back_to_cursor_then_open():
    ed = detect_editor(which=lambda n: "/opt/homebrew/bin/cursor" if n == "cursor" else None,
                       isfile=lambda p: False, platform="darwin")
    assert ed.name == "cursor"

    ed2 = detect_editor(which=lambda n: None, isfile=lambda p: False, platform="darwin")
    assert ed2.name == "open" and ed2.supports_line is False


def test_detect_editor_none_when_no_opener():
    ed = detect_editor(which=lambda n: None, isfile=lambda p: False, platform="linux")
    # No xdg-open either.
    assert ed is None


# --- build_open_argv --------------------------------------------------------

def test_build_argv_code_with_line_col():
    ed = Editor("code", "/usr/bin/code", True)
    assert build_open_argv(ed, "/a.py", 12, 4) == ["/usr/bin/code", "-g", "/a.py:12:4"]


def test_build_argv_code_line_only():
    ed = Editor("code", "/usr/bin/code", True)
    assert build_open_argv(ed, "/a.py", 12, None) == ["/usr/bin/code", "-g", "/a.py:12"]


def test_build_argv_code_no_line():
    ed = Editor("code", "/usr/bin/code", True)
    assert build_open_argv(ed, "/a.py", None, None) == ["/usr/bin/code", "-g", "/a.py"]


def test_build_argv_open_ignores_line():
    ed = Editor("open", "/usr/bin/open", False)
    assert build_open_argv(ed, "/a.py", 12, 4) == ["/usr/bin/open", "/a.py"]


def test_build_argv_startfile_sentinel_is_none():
    ed = Editor("startfile", "startfile", False)
    assert build_open_argv(ed, "/a.py", 1, 1) is None


# --- child_cwd --------------------------------------------------------------

def test_child_cwd_linux_readlink():
    got = child_cwd(123, platform="linux", readlink=lambda p: "/proc-cwd" if p == "/proc/123/cwd" else None)
    assert got == "/proc-cwd"


def test_child_cwd_darwin_parses_lsof():
    class _Proc:
        stdout = "p123\nfcwd\nn/Users/x/live\n"

    got = child_cwd(123, platform="darwin", run=lambda *a, **k: _Proc())
    assert got == "/Users/x/live"


def test_child_cwd_none_without_pid():
    assert child_cwd(None) is None


def test_child_cwd_swallows_errors():
    def _boom(*a, **k):
        raise OSError("nope")

    assert child_cwd(123, platform="linux", readlink=_boom) is None


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
    register_terminal_routes(app, manager=_FakeManager())
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

    monkeypatch.setattr("quodeq.api.terminal_routes.subprocess.Popen", _popen)
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
    monkeypatch.setattr("quodeq.api.terminal_routes.subprocess.Popen",
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
    monkeypatch.setattr("quodeq.api.terminal_routes.subprocess.Popen",
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

    monkeypatch.setattr("quodeq.api.terminal_routes.subprocess.Popen", _boom)
    c = app.test_client()
    r = c.post("/api/terminal/open", json={"path": "/proj/a.py"}, headers=_H, base_url="http://localhost")
    assert r.status_code == 200
    assert r.get_json() == {"opened": False, "editor": "code"}


def test_open_route_requires_path(app):
    c = app.test_client()
    r = c.post("/api/terminal/open", json={}, headers=_H, base_url="http://localhost")
    assert r.status_code == 400
