"""Tests for DELETE /api/shared/config.

Split from test_routes_shared.py (further split out of the "config" topic
to stay under the file-size cap). Read-only invariant: no finding-mutation
routes exist under /api/shared/* or /api/projects/<project>/publish.
Shared fixtures live in tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time

from quodeq.data.fs.shared_repo import (
    clone_lock,
    ensure_shared_clone,
    shared_cache_dir,
    shared_repo_path,
)
from quodeq.services import shared_connect_job, shared_refresh_job
from quodeq.services.shared_connect_job import ConnectJobStatus
from tests._timeouts import budget
from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)

_CONFIRMED = "/api/shared/config?confirm=true"


def test_delete_config_clears(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.delete(_CONFIRMED, headers=_ORIGIN)
    assert resp.status_code == 200
    assert client.get("/api/shared/status").get_json()["configured"] is False


def test_delete_config_removes_cache_dir(client, monkeypatch, tmp_path):
    """Disconnect must remove the clone's cache dir from disk, not
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
    resp = client.delete(_CONFIRMED, headers=_ORIGIN)
    assert resp.status_code == 200
    assert not cache_dir.exists()


def test_delete_config_without_confirm_is_refused_and_keeps_the_clone(client, monkeypatch, tmp_path):
    """Disconnect deletes the local clone for good, so it needs ?confirm=true."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    url = f"file://{origin}"
    assert ensure_shared_clone(url) is not None
    (tmp_path / "shared.json").write_text(json.dumps({"url": url}))

    for path in ("/api/shared/config", "/api/shared/config?confirm=1", "/api/shared/config?confirm=false"):
        resp = client.delete(path, headers=_ORIGIN)
        assert resp.status_code == 400, path
        assert resp.get_json()["code"] == "CONFIRMATION_REQUIRED"
    assert shared_cache_dir(url).is_dir()
    assert client.get("/api/shared/status").get_json()["configured"] is True


def test_delete_config_refused_while_connecting(client, monkeypatch, tmp_path):
    """A running connect job would write its settings after the disconnect
    and silently reconnect, so DELETE answers 409 and changes nothing."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    status = ConnectJobStatus()
    status.claim("git@github.com:t/r.git")
    monkeypatch.setattr(shared_connect_job, "_default_status", status)
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.delete(_CONFIRMED, headers=_ORIGIN)
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "CONNECT_IN_PROGRESS"
    assert client.get("/api/shared/status").get_json()["configured"] is True


def test_delete_config_refused_while_refreshing(client, monkeypatch, tmp_path):
    """A running refresh is rewriting the clone DELETE would remove, so
    DELETE answers 409 and changes nothing."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    status = shared_refresh_job.RefreshStatus()
    status.claim("git@github.com:t/r.git")
    monkeypatch.setattr(shared_refresh_job, "_default_status", status)
    (tmp_path / "shared.json").write_text(json.dumps({"url": "git@github.com:t/r.git"}))
    resp = client.delete(_CONFIRMED, headers=_ORIGIN)
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "REFRESH_IN_PROGRESS"
    assert client.get("/api/shared/status").get_json()["configured"] is True


def test_delete_config_when_unconfigured_does_not_crash(client, monkeypatch, tmp_path):
    """Guard for url=None: disconnecting when nothing is configured must be
    a no-op, not attempt shutil.rmtree on a None-derived path."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.delete(_CONFIRMED, headers=_ORIGIN)
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
            release_lock.wait(timeout=budget(5))

    holder = threading.Thread(target=_hold_lock, name="holder")
    holder.start()
    assert lock_acquired.wait(timeout=budget(5)), "lock holder thread never acquired the lock"

    results: list = []
    # A fresh, un-entered client (rather than the fixture's own `client`,
    # which is held open via `with app.test_client() as c:` for the whole
    # test) keeps this background thread's request/app-context push+pop
    # self-contained instead of racing the fixture's context teardown.
    bg_client = client.application.test_client()

    def _do_delete():
        results.append(bg_client.delete(_CONFIRMED, headers=_ORIGIN))

    delete_thread = threading.Thread(target=_do_delete, name="delete")
    delete_thread.start()

    # Give the DELETE thread a moment to reach (and block on) the lock.
    time.sleep(0.2)
    assert delete_thread.is_alive(), "DELETE returned without waiting for the clone lock"
    assert cache_dir.exists(), "cache dir was removed while the clone lock was still held"

    release_lock.set()
    delete_thread.join(timeout=budget(5))
    holder.join(timeout=budget(5))

    assert not delete_thread.is_alive(), "DELETE deadlocked waiting for the clone lock"
    assert not holder.is_alive()
    assert not cache_dir.exists()
    assert results[0].status_code == 200
