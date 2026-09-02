"""Tests for POST /api/shared/refresh and POST /api/projects/<project>/publish.

Split from test_routes_shared.py. Read-only invariant: no finding-mutation
routes exist under /api/shared/* or /api/projects/<project>/publish.
Shared fixtures live in tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

import json

from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)


def test_refresh_without_config_400(client):
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 400


def test_refresh_failure_returns_502(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr(
        "quodeq.api.routes_shared.refresh_shared_clone",
        lambda url: (False, "Could not resolve host"),
    )
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["stale"] is True


def test_refresh_failure_body_carries_error_reason(client, tmp_path, monkeypatch):
    """Audit B3: the 502 body must carry the failure reason so the UI can
    distinguish DNS vs auth vs a deleted origin, instead of only ever being
    able to render "Request failed: 502"."""
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr(
        "quodeq.api.routes_shared.refresh_shared_clone",
        lambda url: (False, "Could not resolve host github.com"),
    )
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["error"] == "Could not resolve host github.com"


def test_refresh_success_200(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr(
        "quodeq.api.routes_shared.refresh_shared_clone", lambda url: (True, "")
    )
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["stale"] is False


def test_publish_without_config_400(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 400


def test_publish_conflict_returns_409(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr(
        "quodeq.api.routes_shared.start_publish", lambda *a, **kw: "already_running"
    )
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 409
    assert "already running" in resp.get_json()["error"]


def test_publish_thread_start_failure_returns_500_not_409(client, tmp_path, monkeypatch):
    """A thread-start failure is a server error, not "a publish is already running"."""
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared.start_publish", lambda *a, **kw: "failed")
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 500
    assert "already running" not in resp.get_json()["error"]


def test_publish_started_returns_202(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared.start_publish", lambda *a, **kw: "started")
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 202
    assert resp.get_json()["started"] is True


def test_publish_rejects_path_traversal_project_segment(client, tmp_path, monkeypatch):
    """POST /api/projects/../publish must not reach start_publish with a
    project id that can escape the evaluations root.
    """
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    called = {"n": 0}
    monkeypatch.setattr(
        "quodeq.api.routes_shared.start_publish",
        lambda *a, **kw: called.__setitem__("n", called["n"] + 1) or "started",
    )

    resp = client.post("/api/projects/%2e%2e/publish", headers=_ORIGIN)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    assert called["n"] == 0
