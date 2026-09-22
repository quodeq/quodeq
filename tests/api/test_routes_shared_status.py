"""Tests for GET /api/shared/status.

Split from test_routes_shared.py. Read-only invariant: no finding-mutation
routes exist under /api/shared/* or /api/projects/<project>/publish.
Shared fixtures live in tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

import json

from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _clean_publish_status,
    client,
)


def test_shared_status_unconfigured(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is False
    assert body["url"] is None
    assert body["lastSynced"] is None
    assert body["repoState"] is None
    assert "publish" in body


def test_shared_status_configured(client, tmp_path):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is True
    assert body["url"] == "git@github.com:t/r.git"


def test_shared_status_repo_state_reflects_read_state(client, tmp_path):
    """Audit A1: /status must report the real clone state, not just whether
    a URL is configured -- a configured-but-never-cloned URL is "missing"."""
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    assert resp.get_json()["repoState"] == "missing"


def test_shared_status_survives_non_string_url_in_settings_file(client, tmp_path):
    """A hand-edited shared.json with a non-string url must not 500 the status route."""
    (tmp_path / "shared.json").write_text(json.dumps({"url": 123}))
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is False
    assert body["url"] is None


def test_shared_status_shape_is_camel_case_with_top_level_error(client):
    """The phase-2/3 UI binds to this shape: camelCase keys, error always present."""
    body = client.get("/api/shared/status").get_json()
    assert body["error"] is None
    publish = body["publish"]
    assert "finishedAt" in publish
    assert "finished_at" not in publish
