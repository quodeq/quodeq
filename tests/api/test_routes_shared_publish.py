"""Tests for POST /api/shared/refresh and POST /api/projects/<project>/publish.

Split from test_routes_shared.py. Read-only invariant: no finding-mutation
routes exist under /api/shared/* or /api/projects/<project>/publish.
Shared fixtures live in tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

import functools
import json

from quodeq.services import shared_refresh_job
from quodeq.services.shared_refresh_job import RefreshState, RefreshStatus

from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)


def test_refresh_without_config_400(client):
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 400


def _inline_refresh(monkeypatch, status, refresh_fn):
    monkeypatch.setattr(shared_refresh_job, "_default_status", status)
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.start_refresh",
        functools.partial(shared_refresh_job.start_refresh, spawn=lambda fn: fn()),
    )
    monkeypatch.setattr("quodeq.services.shared_refresh_job.refresh_shared_clone", refresh_fn)
    monkeypatch.setattr("quodeq.services.shared_refresh_job.sync_shared_index", lambda url: None)


def test_refresh_starts_job_202(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    status = RefreshStatus()
    _inline_refresh(monkeypatch, status, lambda url, env=None, progress=None: (True, ""))
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 202
    assert resp.get_json() == {"started": True}
    assert status.copy()["state"] == RefreshState.DONE


def test_refresh_failure_lands_in_slot_with_code(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    status = RefreshStatus()
    _inline_refresh(monkeypatch, status, lambda url, env=None, progress=None: (False, "Could not resolve host"))
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 202
    slot = client.get("/api/shared/status").get_json()["refresh"]
    assert slot["state"] == "error" and slot["code"] == "REFRESH_FAILED"
    assert slot["error"] == "Could not resolve host"


def test_refresh_while_running_is_409(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    status = RefreshStatus()
    status.claim("git@github.com:t/r.git")
    _inline_refresh(monkeypatch, status, lambda url, env=None, progress=None: (True, ""))
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "REFRESH_IN_PROGRESS"


def test_publish_without_config_400(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 400


def test_publish_conflict_returns_409(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: "already_running"
    )
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 409
    assert "already running" in resp.get_json()["error"]


def test_publish_conflict_has_code(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: "already_running"
    )
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "PUBLISH_IN_PROGRESS"


def test_publish_thread_start_failure_returns_500_not_409(client, tmp_path, monkeypatch):
    """A thread-start failure is a server error, not "a publish is already running"."""
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: "failed")
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 500
    assert "already running" not in resp.get_json()["error"]


def test_publish_start_failure_has_code(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: "failed")
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 500
    assert resp.get_json()["code"] == "PUBLISH_START_FAILED"


def test_publish_started_returns_202(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared_config.start_publish", lambda *a, **kw: "started")
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
        "quodeq.api.routes_shared_config.start_publish",
        lambda *a, **kw: called.__setitem__("n", called["n"] + 1) or "started",
    )

    resp = client.post("/api/projects/%2e%2e/publish", headers=_ORIGIN)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    assert called["n"] == 0
