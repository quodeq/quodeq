"""Tests for GET /api/browse's error-mapping (403/404/400).

Route-level coverage for _BROWSE_ERROR_MAP was missing entirely before this
suite: the provider's error_code -> HTTP mapping (browse_repo already does
the boundary/existence/directory checks in services/tooling_mixin.py) was
only exercised at the provider layer, never through the Flask route.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.routes_discovery import register_discovery_routes
from quodeq.services.filesystem import FilesystemActionProvider


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_discovery_routes(app, FilesystemActionProvider())
    return app.test_client()


def test_browse_outside_home_returns_403(client, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with patch("pathlib.Path.home", return_value=home):
        resp = client.get(f"/api/browse?path={outside}")
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["code"] == "FORBIDDEN"
    assert body["error"] == "Path must be within the user's home directory"


def test_browse_nonexistent_path_returns_404(client, tmp_path):
    with patch("pathlib.Path.home", return_value=tmp_path):
        resp = client.get(f"/api/browse?path={tmp_path / 'does-not-exist'}")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert body["error"] == "Path not found or not accessible"


def test_browse_path_not_a_directory_returns_400(client, tmp_path):
    a_file = tmp_path / "a_file.txt"
    a_file.write_text("not a directory")
    with patch("pathlib.Path.home", return_value=tmp_path):
        resp = client.get(f"/api/browse?path={a_file}")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert body["error"] == "Path is not a directory"


def test_browse_valid_path_returns_200(client, tmp_path):
    (tmp_path / "sub").mkdir()
    with patch("pathlib.Path.home", return_value=tmp_path):
        resp = client.get(f"/api/browse?path={tmp_path}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["current"] == str(tmp_path)


# ── GET /api/ai-clients/<id>/cmd-path-check ─────────────────────────────
#
# Eager validation for the Settings "command override" field: same rules
# as the aiCmdPath check on POST /api/evaluations, but returned as data
# ({ok, error}) so the UI can flag a bad value at save time instead of
# the user discovering it when a start fails.

def _make_executable(directory, name):
    import os
    import stat
    if os.name == "nt":
        path = directory / f"{name}.bat"
        path.write_text("@exit /b 0\n")
        return str(path)
    path = directory / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


@pytest.fixture()
def bin_dir(tmp_path, monkeypatch):
    import os
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setenv("PATH", f"{d}{os.pathsep}{os.environ.get('PATH', '')}")
    return d


def test_cmd_path_check_valid_bare_name(client, bin_dir):
    _make_executable(bin_dir, "claude-api")
    resp = client.get("/api/ai-clients/claude/cmd-path-check?path=claude-api")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "error": None}


def test_cmd_path_check_missing_binary(client, bin_dir):
    resp = client.get("/api/ai-clients/claude/cmd-path-check?path=claude-nowhere")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is False
    assert "not found" in body["error"]


def test_cmd_path_check_wrong_prefix(client, bin_dir):
    _make_executable(bin_dir, "my-claude")
    resp = client.get("/api/ai-clients/claude/cmd-path-check?path=my-claude")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is False
    assert "must start with 'claude'" in body["error"]


def test_cmd_path_check_empty_path_is_valid(client):
    resp = client.get("/api/ai-clients/claude/cmd-path-check")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "error": None}
