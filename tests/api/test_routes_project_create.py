"""Tests for POST /api/projects with cloneDest / ephemeral support (Task A3)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    evaluations_dir = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evaluations_dir))
    app = create_app(test_config={"TESTING": True})
    home = tmp_path.resolve()
    with app.test_client() as c, patch(
        "pathlib.Path.home", new=classmethod(lambda cls: home)
    ):
        yield c


def test_post_projects_url_requires_clone_dest_or_ephemeral(client):
    resp = client.post(
        "/api/projects", json={"repo": "https://github.com/x/y.git"}, headers=_ORIGIN
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "MISSING_CLONE_DEST"


def test_post_projects_url_with_clone_dest_returns_real_scan(client, tmp_path):
    # cloneDest must be under home (the fixture sets home to tmp_path).
    parent = tmp_path / "code"
    parent.mkdir()

    def fake_register(repo, discipline, reports_dir, scope_path=None, **kw):
        uuid = "test-uuid"
        d = Path(reports_dir) / uuid
        d.mkdir(parents=True, exist_ok=True)
        (d / "scan.json").write_text(json.dumps({"total_files": 5, "code_files": 5}))
        (d / "repository_info.json").write_text(json.dumps({
            "location": "local", "path": str(parent / "y"),
        }))
        return uuid

    with patch(
        "quodeq.services.evaluation_mixin._register_project", side_effect=fake_register
    ):
        resp = client.post(
            "/api/projects",
            json={
                "repo": "https://github.com/x/y.git",
                "cloneDest": str(parent),
            },
            headers=_ORIGIN,
        )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["projectId"] == "test-uuid"
    assert body["scanData"]["total_files"] == 5


def test_post_projects_url_ephemeral_skips_clone_dest(client, tmp_path):
    def fake_register(repo, discipline, reports_dir, scope_path=None, **kw):
        assert kw.get("ephemeral") is True
        assert kw.get("clone_dest") is None
        uuid = "ephemeral-uuid"
        d = Path(reports_dir) / uuid
        d.mkdir(parents=True, exist_ok=True)
        (d / "scan.json").write_text(json.dumps({"total_files": 3}))
        (d / "repository_info.json").write_text(json.dumps({
            "location": "local", "ephemeral": True,
        }))
        return uuid

    with patch(
        "quodeq.services.evaluation_mixin._register_project", side_effect=fake_register
    ):
        resp = client.post(
            "/api/projects",
            json={
                "repo": "https://github.com/x/y.git",
                "ephemeral": True,
            },
            headers=_ORIGIN,
        )
    assert resp.status_code == 200, resp.get_json()


def test_post_projects_rejects_metadata_endpoint_ssrf(client):
    """SSRF: POST /api/projects pointed at a cloud metadata endpoint is rejected
    with 400 and never reaches git clone."""
    clone_calls = []
    with patch(
        "quodeq.services.evaluation_mixin.run_git_clone",
        side_effect=lambda url, dest: clone_calls.append(url),
    ):
        resp = client.post(
            "/api/projects",
            json={"repo": "https://169.254.169.254/latest/meta-data", "ephemeral": True},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["code"] == "INVALID_REPO"
    assert clone_calls == [], "SSRF: git clone must never run for a metadata-endpoint URL"


def test_post_projects_clone_dest_must_exist(client, tmp_path):
    nonexistent = tmp_path / "no-such-dir"
    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": str(nonexistent),
        },
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_CLONE_DEST"


def test_post_projects_clone_dest_must_be_directory_not_file(client, tmp_path):
    """If cloneDest points to a file (not a directory), reject with INVALID_CLONE_DEST."""
    # Fixture sets home to tmp_path, so a file under tmp_path is "under home" but not a dir.
    a_file = tmp_path / "regular-file.txt"
    a_file.write_text("not a directory")

    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": str(a_file),
        },
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_CLONE_DEST"


def test_post_projects_clone_dest_must_be_under_home(client, tmp_path):
    """If cloneDest resolves outside the user's home folder, reject with INVALID_CLONE_DEST."""
    # Fixture pins home to tmp_path. Build a sibling path that exists but is outside home.
    outside = tmp_path.parent / "outside-home-dir"
    outside.mkdir(exist_ok=True)

    resp = client.post(
        "/api/projects",
        json={
            "repo": "https://github.com/x/y.git",
            "cloneDest": str(outside),
        },
        headers=_ORIGIN,
    )
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_CLONE_DEST"
