"""Tests for the shared results repository API routes: config, status,
refresh, publish. Read-only invariant: no finding-mutation routes exist
under /api/shared/* or /api/projects/<project>/publish.
"""
from __future__ import annotations

import json

import pytest

from quodeq.api.app import create_app
from quodeq.services import shared_publish

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_publish_status():
    """Snapshot and restore the module-level publish status dict.

    ``shared_publish._STATUS`` is a process-global mutated by the real
    publish job (tests/services/test_shared_publish_job.py) and by the
    monkeypatched routes below, so each test here must start and end from
    a clean slate to stay hermetic across the whole suite.
    """
    with shared_publish._STATUS_LOCK:
        snapshot = dict(shared_publish._STATUS)
    yield
    with shared_publish._STATUS_LOCK:
        shared_publish._STATUS.clear()
        shared_publish._STATUS.update(snapshot)


# --- GET /api/shared/status --------------------------------------------------

def test_shared_status_unconfigured(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is False
    assert body["url"] is None
    assert body["lastSynced"] is None
    assert "publish" in body


def test_shared_status_configured(client, tmp_path):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is True
    assert body["url"] == "git@github.com:t/r.git"


# --- PUT /api/shared/config ---------------------------------------------------

def test_put_config_rejects_invalid_url(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.put("/api/shared/config", json={"url": "not a url"}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_put_config_rejects_private_host(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.put(
        "/api/shared/config", json={"url": "https://127.0.0.1/x/y.git"}, headers=_ORIGIN
    )
    assert resp.status_code == 400


def test_put_config_requires_url(client):
    resp = client.put("/api/shared/config", json={}, headers=_ORIGIN)
    assert resp.status_code == 400


def test_put_config_rejects_non_string_url(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.put("/api/shared/config", json={"url": 123}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_put_config_clone_failure_returns_502(client, monkeypatch):
    monkeypatch.setattr("quodeq.api.routes_shared.validate_remote_url", lambda url: None)
    monkeypatch.setattr("quodeq.api.routes_shared.ensure_shared_clone", lambda url: None)
    resp = client.put(
        "/api/shared/config",
        json={"url": "https://github.com/example/repo.git"},
        headers=_ORIGIN,
    )
    assert resp.status_code == 502
    assert "error" in resp.get_json()


def test_put_config_happy_path(client, monkeypatch, tmp_path):
    fake_repo = tmp_path / "fake-clone"
    fake_repo.mkdir()
    monkeypatch.setattr("quodeq.api.routes_shared.validate_remote_url", lambda url: None)
    monkeypatch.setattr("quodeq.api.routes_shared.ensure_shared_clone", lambda url: fake_repo)
    resp = client.put(
        "/api/shared/config",
        json={"url": "https://github.com/example/repo.git"},
        headers=_ORIGIN,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["configured"] is True
    assert body["url"] == "https://github.com/example/repo.git"

    status = client.get("/api/shared/status").get_json()
    assert status["configured"] is True
    assert status["url"] == "https://github.com/example/repo.git"


# --- DELETE /api/shared/config -----------------------------------------------

def test_delete_config_clears(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.delete("/api/shared/config", headers=_ORIGIN)
    assert resp.status_code == 200
    assert client.get("/api/shared/status").get_json()["configured"] is False


# --- POST /api/shared/refresh -------------------------------------------------

def test_refresh_without_config_400(client):
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 400


def test_refresh_failure_returns_502(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared.refresh_shared_clone", lambda url: False)
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["stale"] is True


def test_refresh_success_200(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared.refresh_shared_clone", lambda url: True)
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["stale"] is False


# --- POST /api/projects/<project>/publish -------------------------------------

def test_publish_without_config_400(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 400


def test_publish_conflict_returns_409(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared.start_publish", lambda *a, **kw: False)
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 409


def test_publish_started_returns_202(client, tmp_path, monkeypatch):
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    monkeypatch.setattr("quodeq.api.routes_shared.start_publish", lambda *a, **kw: True)
    resp = client.post("/api/projects/some-proj/publish", headers=_ORIGIN)
    assert resp.status_code == 202
    assert resp.get_json()["started"] is True
