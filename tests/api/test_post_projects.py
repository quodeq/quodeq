"""Tests for POST /api/projects endpoint (onboarding wizard scan-only registration)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    # Redirect the reports directory so registration writes under tmp_path.
    evaluations_dir = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evaluations_dir))
    app = create_app(test_config={"TESTING": True})
    home = tmp_path.resolve()
    with app.test_client() as c:
        yield c, home, tmp_path


def _patch_home(home: Path):
    return patch("pathlib.Path.home", new=classmethod(lambda cls: home))


def _make_local_repo(parent: Path, name: str = "myrepo") -> Path:
    repo = parent / name
    repo.mkdir()
    (repo / "main.py").write_text("def hello():\n    return 'world'\n")
    (repo / ".git").mkdir()  # marker so quodeq treats as git repo
    return repo


def test_post_projects_local_path_registers_and_returns_scan_data(app_client, tmp_path):
    c, home, _ = app_client
    repo = _make_local_repo(home)
    with _patch_home(home):
        resp = c.post(
            "/api/projects",
            json={"repo": str(repo)},
            headers=_ORIGIN,
        )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "projectId" in body
    assert "scanData" in body
    assert body["scanData"]["total_files"] >= 1


def test_post_projects_missing_repo_returns_400(app_client):
    c, home, _ = app_client
    with _patch_home(home):
        resp = c.post("/api/projects", json={}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert "repo" in resp.get_json().get("error", "").lower()


def test_post_projects_bad_local_path_returns_400_and_no_dir(app_client, tmp_path):
    c, home, _ = app_client
    nonexistent = home / "does-not-exist"
    reports_root = home / "evaluations"  # default reports_dir() under home
    before_dirs = set()
    if reports_root.is_dir():
        before_dirs = {p.name for p in reports_root.iterdir() if p.is_dir()}
    with _patch_home(home):
        resp = c.post("/api/projects", json={"repo": str(nonexistent)}, headers=_ORIGIN)
    assert resp.status_code == 400
    after_dirs = set()
    if reports_root.is_dir():
        after_dirs = {p.name for p in reports_root.iterdir() if p.is_dir()}
    assert after_dirs == before_dirs, "Rollback should leave no new project directory on disk"


def test_post_projects_duplicate_returns_409(app_client, tmp_path):
    c, home, _ = app_client
    repo = _make_local_repo(home, "dupe-repo")
    with _patch_home(home):
        first = c.post("/api/projects", json={"repo": str(repo)}, headers=_ORIGIN)
        assert first.status_code == 200
        first_id = first.get_json()["projectId"]

        second = c.post("/api/projects", json={"repo": str(repo)}, headers=_ORIGIN)
    assert second.status_code == 409
    body = second.get_json()
    assert body.get("existingProjectId") == first_id


def test_post_projects_writes_onboarding_field_null(app_client):
    c, home, _ = app_client
    repo = _make_local_repo(home, "field-repo")
    with _patch_home(home):
        resp = c.post("/api/projects", json={"repo": str(repo)}, headers=_ORIGIN)
    assert resp.status_code == 200
    project_id = resp.get_json()["projectId"]
    info_path = home / "evaluations" / project_id / "repository_info.json"
    assert info_path.exists()
    data = json.loads(info_path.read_text())
    assert "onboardingCompletedAt" in data
    assert data["onboardingCompletedAt"] is None
