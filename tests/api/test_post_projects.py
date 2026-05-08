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
    reports_root = home / "evaluations"  # QUODEQ_EVALUATIONS_DIR points here per fixture setup
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


def test_post_projects_cleartext_http_returns_400(app_client):
    c, home, _ = app_client
    with _patch_home(home):
        resp = c.post(
            "/api/projects",
            json={"repo": "http://example.com/x"},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body.get("code") == "INVALID_REPO_URL"


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


def test_get_projects_backfills_onboarding_field_for_legacy_projects(app_client, tmp_path):
    c, home, _ = app_client
    # Manually create a "legacy" project record without onboardingCompletedAt
    reports_root = home / "evaluations"
    reports_root.mkdir(parents=True, exist_ok=True)
    legacy_id = "legacy-uuid-1234"
    legacy_dir = reports_root / legacy_id
    legacy_dir.mkdir()
    info = legacy_dir / "repository_info.json"
    info.write_text(json.dumps({
        "name": "legacy-project",
        "repository": "/some/legacy/path",
        "createdAt": "2025-12-01T00:00:00Z",
        "location": "local",
    }))
    # Add a minimal run so the project surfaces in the listing.
    run_dir = legacy_dir / "2025-12-01_00-00-00"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text(json.dumps({"language_stats": {}}))

    with _patch_home(home):
        resp = c.get("/api/projects", headers=_ORIGIN)
    assert resp.status_code == 200

    # The on-disk file should now have onboardingCompletedAt populated.
    data = json.loads(info.read_text())
    assert "onboardingCompletedAt" in data
    assert data["onboardingCompletedAt"] == "2025-12-01T00:00:00Z"

    # The field should also surface in the API response so the UI can
    # decide whether to auto-open the wizard without re-reading disk.
    body = resp.get_json()
    projects = body["projects"] if isinstance(body, dict) else body
    target = next(
        (
            p for p in projects
            if p.get("id") == legacy_id or p.get("name") == "legacy-project"
        ),
        None,
    )
    assert target is not None, f"legacy project not in response: {projects}"
    assert target.get("onboardingCompletedAt") == "2025-12-01T00:00:00Z"
