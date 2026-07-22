"""Tests for the shared results repository API routes: config, status,
refresh, publish. Read-only invariant: no finding-mutation routes exist
under /api/shared/* or /api/projects/<project>/publish.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services import shared_publish
from quodeq.services.shared_repo import (
    FORMAT_NAME,
    clone_lock,
    ensure_shared_clone,
    shared_cache_dir,
    shared_repo_path,
)

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


def test_put_config_reconnect_refreshes_pre_existing_clone(client, monkeypatch, tmp_path):
    """Audit A4: reconnecting to a URL whose clone already exists in the
    cache must fetch fresh content before returning, not silently keep
    serving whatever was last fetched. Regression: a project is published
    directly to origin AFTER the first connect, then the same URL is
    reconnected (second PUT) -- the listing must already show it, with no
    separate POST /api/shared/refresh in between."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    monkeypatch.setattr("quodeq.api.routes_shared.validate_remote_url", lambda url: None)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    work = tmp_path / "origin-work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    (work / "quodeq.json").write_text(
        json.dumps({"format": FORMAT_NAME, "version": 1}), encoding="utf-8"
    )
    for cmd in (
        ["git", "add", "."],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)

    # First connect clones the (currently project-less) repo.
    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 200
    listing = client.get("/api/shared/projects").get_json()
    assert listing["projects"] == []

    # A new project is published directly to origin, bypassing this
    # process's clone entirely (e.g. a teammate publishing from another
    # machine).
    project_dir = work / "evaluations" / "proj-new"
    project_dir.mkdir(parents=True)
    (project_dir / "repository_info.json").write_text('{"name":"proj-new"}', encoding="utf-8")
    for cmd in (
        ["git", "add", "."],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "publish proj-new"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)

    # Reconnect the SAME url -- the cache dir from the first PUT already
    # exists on disk. Before this fix, ensure_shared_clone early-returns it
    # unfetched, so proj-new would only appear after a manual refresh.
    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 200

    listing = client.get("/api/shared/projects").get_json()
    ids = [p.get("id") or p.get("name") for p in listing["projects"]]
    assert "proj-new" in ids


# --- DELETE /api/shared/config -----------------------------------------------

def test_delete_config_clears(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.delete("/api/shared/config", headers=_ORIGIN)
    assert resp.status_code == 200
    assert client.get("/api/shared/status").get_json()["configured"] is False


def test_delete_config_removes_cache_dir(client, monkeypatch, tmp_path):
    """Audit A4: disconnect must remove the clone's cache dir from disk, not
    just clear settings -- otherwise a stale clone sits around forever."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    assert ensure_shared_clone(url) is not None
    cache_dir = shared_cache_dir(url)
    assert cache_dir.is_dir()
    assert shared_repo_path(url).is_dir()

    (tmp_path / "shared.json").write_text(json.dumps({"url": url}))
    resp = client.delete("/api/shared/config", headers=_ORIGIN)
    assert resp.status_code == 200
    assert not cache_dir.exists()


def test_delete_config_when_unconfigured_does_not_crash(client, monkeypatch, tmp_path):
    """Guard for url=None: disconnecting when nothing is configured must be
    a no-op, not attempt shutil.rmtree on a None-derived path."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.delete("/api/shared/config", headers=_ORIGIN)
    assert resp.status_code == 200
    assert resp.get_json()["configured"] is False


def test_delete_config_waits_for_clone_lock(client, monkeypatch, tmp_path):
    """Review finding: DELETE rmtree'd the cache dir without holding
    clone_lock(url), unlike every other clone mutator (ensure_shared_clone,
    refresh_shared_clone, publish_project). A concurrent publish/refresh
    holding the lock could have its clone directory yanked out from under
    it mid-operation, potentially leaving a partially-deleted .git that
    doesn't self-heal. DELETE must block on the lock before removing the
    cache dir, same as everything else that touches the clone."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    assert ensure_shared_clone(url) is not None
    cache_dir = shared_cache_dir(url)
    assert cache_dir.is_dir()

    (tmp_path / "shared.json").write_text(json.dumps({"url": url}))

    lock = clone_lock(url)
    lock_acquired = threading.Event()
    release_lock = threading.Event()

    def _hold_lock():
        with lock:
            lock_acquired.set()
            release_lock.wait(timeout=5)

    holder = threading.Thread(target=_hold_lock, name="holder")
    holder.start()
    assert lock_acquired.wait(timeout=5), "lock holder thread never acquired the lock"

    results: list = []
    # A fresh, un-entered client (rather than the fixture's own `client`,
    # which is held open via `with app.test_client() as c:` for the whole
    # test) keeps this background thread's request/app-context push+pop
    # self-contained instead of racing the fixture's context teardown.
    bg_client = client.application.test_client()

    def _do_delete():
        results.append(bg_client.delete("/api/shared/config", headers=_ORIGIN))

    delete_thread = threading.Thread(target=_do_delete, name="delete")
    delete_thread.start()

    # Give the DELETE thread a moment to reach (and block on) the lock.
    time.sleep(0.2)
    assert delete_thread.is_alive(), "DELETE returned without waiting for the clone lock"
    assert cache_dir.exists(), "cache dir was removed while the clone lock was still held"

    release_lock.set()
    delete_thread.join(timeout=5)
    holder.join(timeout=5)

    assert not delete_thread.is_alive(), "DELETE deadlocked waiting for the clone lock"
    assert not holder.is_alive()
    assert not cache_dir.exists()
    assert results[0].status_code == 200


# --- POST /api/shared/refresh -------------------------------------------------

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
