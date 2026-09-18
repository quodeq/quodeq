"""Machine-readable error-code coverage for GET /api/ai-clients/<id>/cmd-path-check
(usability cycle 1, task 6 sweep): the one bare jsonify() tools/check_error_codes.py
(the zero-tolerance gate added in task 6) found under routes_discovery.py.

The endpoint always answers 200 with ``{"ok", "error", "code"}``: ``code`` is
None alongside a None ``error`` when the path is valid, and INVALID_INPUT
alongside the reason when it isn't (same rule ``_evaluation_helpers.py``'s
start-evaluation validation uses for the same field).
"""
from __future__ import annotations

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


def test_cmd_path_check_valid_has_null_code(client):
    resp = client.get("/api/ai-clients/claude/cmd-path-check")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["error"] is None
    assert body["code"] is None


def test_cmd_path_check_invalid_has_invalid_input_code(client):
    resp = client.get(
        "/api/ai-clients/claude/cmd-path-check", query_string={"path": "bad path"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"] is not None
    assert body["code"] == "INVALID_INPUT"
