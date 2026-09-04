"""Tests for PUT /api/shared/config.

Split from test_routes_shared.py. Read-only invariant: no finding-mutation
routes exist under /api/shared/* or /api/projects/<project>/publish.
Shared fixtures live in tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quodeq.data.fs.shared_repo import FORMAT_NAME
from quodeq.services.shared_connect import ConnectOutcome
from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)


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


def test_put_shared_config_missing_url_has_code(client):
    resp = client.put("/api/shared/config", json={}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "URL_REQUIRED"


def test_put_shared_config_clone_failed_has_code(client, monkeypatch):
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.connect_shared_repo",
        lambda url: ConnectOutcome(status="clone_failed", url=url),
    )
    resp = client.put(
        "/api/shared/config", json={"url": "https://example.invalid/x.git"}, headers=_ORIGIN
    )
    assert resp.status_code == 502
    assert resp.get_json()["code"] == "CLONE_FAILED"


def test_put_shared_config_foreign_repo_has_code(client, monkeypatch):
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.connect_shared_repo",
        lambda url: ConnectOutcome(status="foreign", url=url),
    )
    resp = client.put(
        "/api/shared/config", json={"url": "https://example.invalid/x.git"}, headers=_ORIGIN
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "FOREIGN_REPO"


def test_put_shared_config_unsupported_version_has_code(client, monkeypatch):
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.connect_shared_repo",
        lambda url: ConnectOutcome(status="unsupported_version", url=url),
    )
    resp = client.put(
        "/api/shared/config", json={"url": "https://example.invalid/x.git"}, headers=_ORIGIN
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "UNSUPPORTED_VERSION"


def test_put_config_rejects_non_string_url(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.put("/api/shared/config", json={"url": 123}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_put_config_clone_failure_returns_502(client, monkeypatch):
    monkeypatch.setattr("quodeq.services.shared_connect.validate_remote_url", lambda url: None)
    monkeypatch.setattr("quodeq.services.shared_connect.ensure_shared_clone", lambda url: None)
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
    monkeypatch.setattr("quodeq.services.shared_connect.validate_remote_url", lambda url: None)
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
    monkeypatch.setattr("quodeq.services.shared_connect.validate_remote_url", lambda url: None)
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
    monkeypatch.setattr("quodeq.services.shared_connect.validate_remote_url", lambda url: None)
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
    monkeypatch.setattr("quodeq.services.shared_connect.validate_remote_url", lambda url: None)
    monkeypatch.setattr("quodeq.services.shared_connect.ensure_shared_clone", lambda url: fake_repo)
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
    monkeypatch.setattr("quodeq.services.shared_connect.validate_remote_url", lambda url: None)
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
