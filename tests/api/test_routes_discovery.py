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
