"""Tests for project listing, mutation, and scan routes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from quodeq.api.routes_project_list import register_project_list_routes

# Path.is_absolute() requires a drive letter on Windows ("/Users/test/code"
# is not absolute there), so use a platform-appropriate sample path for
# routes that validate absolute-ness.
_ABS_SAMPLE_PATH = "C:\\Users\\test\\code" if os.name == "nt" else "/Users/test/code"


class _FakeProvider:
    """Minimal stub implementing the ActionProvider methods used by project routes."""

    def __init__(self):
        self.projects: list[dict] = []
        self.deleted: list[str] = []
        self.updated_paths: dict[str, str] = {}
        self.project_info: dict | None = None

    def list_projects(self, reports_dir: str) -> dict:
        return {"projects": self.projects}

    def delete_project(self, reports_dir: str, project: str) -> bool:
        if project in self.deleted:
            return False
        self.deleted.append(project)
        return True

    def update_project_path(self, reports_dir: str, project: str, new_path: str) -> bool:
        self.updated_paths[project] = new_path
        return True

    def get_project_info(self, reports_dir: str, project: str) -> dict:
        return self.project_info or {}

    def invalidate_projects_cache(self) -> None:
        self.cache_invalidated = True


@pytest.fixture()
def provider():
    return _FakeProvider()


@pytest.fixture()
def app(tmp_path, provider):
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["EVALUATIONS_DIR"] = str(tmp_path)

    with patch("quodeq.api.routes_project_list.reports_dir", return_value=str(tmp_path)):
        register_project_list_routes(flask_app, provider)
        yield flask_app


@pytest.fixture()
def client(app):
    # The app fixture already holds the reports_dir patch open via yield
    return app.test_client()


class TestListProjects:
    def test_returns_empty_list(self, client, provider):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.get_json()["projects"] == []

    def test_returns_projects(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects")
        assert len(resp.get_json()["projects"]) == 3

    def test_pagination_offset(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects?offset=1")
        data = resp.get_json()["projects"]
        assert len(data) == 2
        assert data[0]["name"] == "b"

    def test_pagination_limit(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects?limit=2")
        data = resp.get_json()["projects"]
        assert len(data) == 2

    def test_pagination_offset_and_limit(self, client, provider):
        provider.projects = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        resp = client.get("/api/projects?offset=1&limit=1")
        data = resp.get_json()["projects"]
        assert len(data) == 1
        assert data[0]["name"] == "b"


class TestDeleteProject:
    def test_delete_requires_confirm(self, client):
        resp = client.delete("/api/projects/my-proj")
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "CONFIRMATION_REQUIRED"

    def test_delete_success(self, client, provider):
        resp = client.delete("/api/projects/my-proj?confirm=true")
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] == "my-proj"
        assert "my-proj" in provider.deleted

    def test_delete_not_found(self, client, provider):
        # First delete succeeds, second returns False
        provider.deleted.append("ghost")
        resp = client.delete("/api/projects/ghost?confirm=true")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"


class TestUpdateProjectPath:
    def test_requires_path(self, client):
        resp = client.patch("/api/projects/my-proj/path", json={})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_rejects_relative_path(self, client):
        resp = client.patch("/api/projects/my-proj/path", json={"path": "relative/path"})
        assert resp.status_code == 400

    def test_rejects_path_traversal(self, client):
        resp = client.patch("/api/projects/my-proj/path", json={"path": "/foo/../bar"})
        assert resp.status_code == 400

    def test_update_success(self, client, provider):
        resp = client.patch("/api/projects/my-proj/path", json={"path": _ABS_SAMPLE_PATH})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["updated"] == "my-proj"
        assert body["path"] == str(Path(_ABS_SAMPLE_PATH).resolve(strict=False))

    def test_update_not_found(self, client, provider):
        # Make update_project_path return False
        provider.update_project_path = lambda *a: False
        resp = client.patch("/api/projects/my-proj/path", json={"path": _ABS_SAMPLE_PATH})
        assert resp.status_code == 404


class TestProjectInfo:
    def test_returns_info(self, client, provider):
        provider.project_info = {"name": "proj", "location": "local"}
        resp = client.get("/api/projects/proj/info")
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "proj"

    def test_not_found(self, client, provider):
        provider.project_info = {}
        resp = client.get("/api/projects/proj/info")
        assert resp.status_code == 404


class TestProjectScan:
    def test_project_not_found(self, client, tmp_path):
        resp = client.get("/api/projects/nonexistent/scan")
        assert resp.status_code == 404

    def test_returns_cached_scan(self, client, tmp_path):
        proj_dir = tmp_path / "my-proj"
        proj_dir.mkdir()
        scan_data = {"files": 10, "languages": ["python"]}
        (proj_dir / "scan.json").write_text(json.dumps(scan_data))
        resp = client.get("/api/projects/my-proj/scan")
        assert resp.status_code == 200
        assert resp.get_json()["files"] == 10

    def test_no_scan_no_repo_info(self, client, tmp_path):
        proj_dir = tmp_path / "my-proj"
        proj_dir.mkdir()
        resp = client.get("/api/projects/my-proj/scan")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"

    def test_invalid_repo_info(self, client, tmp_path):
        proj_dir = tmp_path / "my-proj"
        proj_dir.mkdir()
        (proj_dir / "repository_info.json").write_text("not json")
        resp = client.get("/api/projects/my-proj/scan")
        assert resp.status_code == 500

    def test_non_local_project_rejected(self, client, tmp_path):
        proj_dir = tmp_path / "my-proj"
        proj_dir.mkdir()
        (proj_dir / "repository_info.json").write_text(json.dumps({"location": "github", "path": ""}))
        resp = client.get("/api/projects/my-proj/scan")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "NOT_LOCAL"

    def test_local_path_missing(self, client, tmp_path):
        proj_dir = tmp_path / "my-proj"
        proj_dir.mkdir()
        (proj_dir / "repository_info.json").write_text(json.dumps({"location": "local", "path": "/nonexistent/path/abc"}))
        resp = client.get("/api/projects/my-proj/scan")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "PATH_MISSING"


class TestScanPath:
    def test_requires_path(self, client):
        resp = client.post("/api/scan", json={})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PATH"

    def test_path_not_directory(self, client):
        # Use a path under home that doesn't exist to pass the allowlist check
        fake = str(Path.home() / "nonexistent_quodeq_test_path_abc")
        resp = client.post("/api/scan", json={"path": fake})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "NOT_DIR"

    def test_system_dir_blocked(self, client):
        resp = client.post("/api/scan", json={"path": "/etc"})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    def test_outside_home_blocked(self, client):
        resp = client.post("/api/scan", json={"path": "/nonexistent/path/abc"})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    def test_scan_success(self, client, tmp_path):
        target = tmp_path / "code"
        target.mkdir()
        from dataclasses import dataclass

        @dataclass
        class FakeScanResult:
            files: int = 5
            languages: list = None

        with patch("quodeq.services._fs_scan.scan_project", return_value=FakeScanResult(files=5, languages=["py"])), \
             patch("pathlib.Path.home", return_value=tmp_path):
            resp = client.post("/api/scan", json={"path": str(target)})
            assert resp.status_code == 200


class TestCreateProjectLocalPathValidation:
    """SEC-24: the local-repo branch of create_project enforces the same
    allowlist as /api/scan (home or evaluations dir, no system paths)."""

    def test_local_repo_outside_home_rejected(self, client, tmp_path_factory):
        # Pin home to its own temp dir: the candidate repo must be outside it
        # on every platform (on Windows the pytest tmp root lives UNDER the
        # real home, so relying on the real Path.home() would pass the
        # allowlist and return 200).
        fake_home = tmp_path_factory.mktemp("fake-home")
        outside = tmp_path_factory.mktemp("outside-home-repo")
        with patch("pathlib.Path.home", return_value=fake_home):
            resp = client.post("/api/projects", json={"repo": str(outside)})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    @pytest.mark.skipif(
        os.name == "nt",
        reason="blocked paths are POSIX system dirs; /etc does not exist on "
        "Windows so the existence check 400s before the allowlist",
    )
    def test_local_repo_system_dir_rejected(self, client):
        # Widen home to "/" so the allowlist passes and the blocked-path
        # check is the branch under test.
        with patch("pathlib.Path.home", return_value=Path("/")):
            resp = client.post("/api/projects", json={"repo": "/etc"})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "FORBIDDEN"

    def test_local_repo_under_evaluations_root_accepted(self, client, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        with patch(
            "quodeq.services.evaluation_mixin._register_project",
            return_value="uuid-1",
        ):
            resp = client.post("/api/projects", json={"repo": str(repo_dir)})
        assert resp.status_code == 200
        assert resp.get_json()["projectId"] == "uuid-1"

    def test_nonexistent_local_repo_still_400(self, client, tmp_path):
        resp = client.post(
            "/api/projects", json={"repo": str(tmp_path / "does-not-exist")}
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_REPO"
