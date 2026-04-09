"""Tests for project listing, mutation, and scan routes."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from quodeq.api.routes_project_list import register_project_list_routes


class _FakeProvider:
    """Minimal stub implementing the ActionProvider methods used by project routes."""

    def __init__(self):
        self.projects: list[dict] = []
        self.deleted: list[str] = []
        self.updated_paths: dict[str, str] = {}
        self.project_info: dict | None = None
        self.clone_result: dict | None = None

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

    def clone_to_local(self, reports_dir: str, project: str, destination: str) -> dict | None:
        return self.clone_result


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
        resp = client.patch("/api/projects/my-proj/path", json={"path": "/Users/test/code"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["updated"] == "my-proj"
        assert body["path"] == "/Users/test/code"

    def test_update_not_found(self, client, provider):
        # Make update_project_path return False
        provider.update_project_path = lambda *a: False
        resp = client.patch("/api/projects/my-proj/path", json={"path": "/Users/test/code"})
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


class TestCloneProjectLocal:
    def test_requires_destination(self, client):
        resp = client.post("/api/projects/proj/clone-local", json={})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_destination_outside_home_forbidden(self, client):
        resp = client.post("/api/projects/proj/clone-local", json={"destination": "/tmp/evil"})
        assert resp.status_code == 403

    def test_destination_not_found(self, client, tmp_path):
        home = Path.home().resolve()
        fake_dir = home / "nonexistent_quodeq_test_dir_xyz"
        resp = client.post("/api/projects/proj/clone-local", json={"destination": str(fake_dir)})
        assert resp.status_code == 404

    def test_clone_success(self, client, provider, tmp_path):
        home = Path.home().resolve()
        # Use a real directory under $HOME
        dest = home / ".cache"
        if not dest.is_dir():
            pytest.skip("~/.cache not available")
        provider.clone_result = {"project": "proj", "path": str(dest)}
        resp = client.post("/api/projects/proj/clone-local", json={"destination": str(dest)})
        assert resp.status_code == 200

    def test_clone_failure(self, client, provider, tmp_path):
        home = Path.home().resolve()
        dest = home / ".cache"
        if not dest.is_dir():
            pytest.skip("~/.cache not available")
        provider.clone_result = None
        resp = client.post("/api/projects/proj/clone-local", json={"destination": str(dest)})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "CLONE_FAILED"


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
        resp = client.post("/api/scan", json={"path": "/nonexistent/path/abc"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "NOT_DIR"

    def test_scan_success(self, client, tmp_path):
        target = tmp_path / "code"
        target.mkdir()
        from dataclasses import dataclass

        @dataclass
        class FakeScanResult:
            files: int = 5
            languages: list = None

        with patch("quodeq.services._fs_scan.scan_project", return_value=FakeScanResult(files=5, languages=["py"])):
            resp = client.post("/api/scan", json={"path": str(target)})
            assert resp.status_code == 200
