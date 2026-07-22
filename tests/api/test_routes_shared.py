"""Tests for the shared results repository API routes: config, status,
refresh, publish. Read-only invariant: no finding-mutation routes exist
under /api/shared/* or /api/projects/<project>/publish.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services import shared_publish
from quodeq.services.shared_repo import FORMAT_NAME

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


def _push_seed_file(origin: Path, name: str, content: str) -> None:
    work = origin.parent / f"{origin.stem}-seed"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    (work / name).write_text(content, encoding="utf-8")
    for cmd in (
        ["git", "add", "."],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)


def test_put_config_rejects_foreign_repo_after_clone(client, monkeypatch, tmp_path):
    """Audit A1: PUT must validate format AFTER a real clone succeeds --
    a real, clonable git repo that isn't a quodeq results repo (no
    quodeq.json marker) is rejected, and settings are never written for it.
    """
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    # validate_remote_url legitimately rejects file:// (SSRF guard scopes
    # accepted schemes to https/ssh); bypass just that check so the local
    # bare origin below can exercise the real clone + format-check path.
    monkeypatch.setattr("quodeq.api.routes_shared.validate_remote_url", lambda url: None)
    origin = tmp_path / "foreign-origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    _push_seed_file(origin, "README.md", "some other project")
    url = f"file://{origin}"

    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == (
        "the repository exists but does not look like a quodeq results repository"
    )

    status = client.get("/api/shared/status").get_json()
    assert status["configured"] is False
    assert status["url"] is None


def test_put_config_rejects_unsupported_version_after_clone(client, monkeypatch, tmp_path):
    """Audit A1: same AFTER-clone validation for a repo whose quodeq.json
    marker declares a format version newer than this build understands."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setattr("quodeq.api.routes_shared.validate_remote_url", lambda url: None)
    origin = tmp_path / "future-origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    _push_seed_file(
        origin, "quodeq.json", json.dumps({"format": FORMAT_NAME, "version": 99}),
    )
    url = f"file://{origin}"

    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "this shared repository requires a newer version of quodeq"

    status = client.get("/api/shared/status").get_json()
    assert status["configured"] is False
    assert status["url"] is None


def test_put_config_accepts_empty_repo(client, monkeypatch, tmp_path):
    """Audit A1: a real clone of a bare origin with zero commits ("empty",
    never published into) must be accepted, not rejected as foreign."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setattr("quodeq.api.routes_shared.validate_remote_url", lambda url: None)
    origin = tmp_path / "empty-origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"

    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 200
    assert resp.get_json()["configured"] is True

    status = client.get("/api/shared/status").get_json()
    assert status["configured"] is True
    assert status["url"] == url


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
