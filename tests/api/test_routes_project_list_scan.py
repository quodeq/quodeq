"""Tests for project scan status, /api/scan, and /api/projects/<p>/estimates.

Split from test_routes_project_list.py. Shared fixtures
(_FakeProvider/provider/app/client) live in
tests/api/_routes_project_list_fixtures.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)


class TestProjectScan:
    def test_project_not_found(self, client, tmp_path):
        resp = client.get("/api/projects/nonexistent/scan")
        assert resp.status_code == 404

    def test_rejects_traversal_project_name(self, client):
        resp = client.get("/api/projects/../scan")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"

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


class TestProjectEstimates:
    """GET /api/projects/<project>/estimates — read-only pre-run estimates."""

    @pytest.fixture(autouse=True)
    def _isolated_cache(self, tmp_path, monkeypatch):
        # Keep the result cache off the developer's real ~/.quodeq/cache so
        # every estimate here sees a cold cache deterministically.
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))

    def _setup_project(self, tmp_path, name="my-proj", files=("a.py", "b.py", "c.py")):
        """Create a registered project pointing at a tiny local repo.

        Three files minimum: the manifest builder drops languages with
        fewer than _MIN_FILES_PER_TARGET (3) files.
        """
        repo = tmp_path / "repo"
        repo.mkdir(exist_ok=True)
        for f in files:
            (repo / f).write_text(f"# {f}\n")
        proj_dir = tmp_path / name
        proj_dir.mkdir()
        (proj_dir / "repository_info.json").write_text(
            json.dumps({"name": name, "location": "local", "path": str(repo)})
        )
        return repo

    def test_unknown_project_404(self, client):
        resp = client.get("/api/projects/nonexistent/estimates")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"

    def test_rejects_traversal_project_name(self, client):
        resp = client.get("/api/projects/../estimates")
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_happy_path_with_dimensions_param(self, client, tmp_path):
        self._setup_project(tmp_path)
        resp = client.get("/api/projects/my-proj/estimates?dimensions=security")
        assert resp.status_code == 200
        body = resp.get_json()
        assert set(body["dimensions"].keys()) == {"security"}
        sec = body["dimensions"]["security"]
        assert sec["count"] == 3
        assert sec["total"] == 3
        assert sec["cached"] == 0
        assert sec["excluded"] == 0
        # Cold cache in incremental mode: every file is a miss.
        assert sec["reason"] == "first-run"
        assert body["projectFiles"] == 3
        assert body["changedFiles"] == 3
        assert body["cachedFiles"] == 0

    def test_omitted_dimensions_estimates_all(self, client, tmp_path):
        self._setup_project(tmp_path)
        resp = client.get("/api/projects/my-proj/estimates")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "security" in body["dimensions"]
        assert len(body["dimensions"]) > 1
        assert all(d["total"] == 3 for d in body["dimensions"].values())

    def test_clean_scan_zeroes_cached(self, client, tmp_path):
        self._setup_project(tmp_path)
        resp = client.get(
            "/api/projects/my-proj/estimates?dimensions=security&cleanScan=true"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        sec = body["dimensions"]["security"]
        assert sec["reason"] == "full"
        assert sec["count"] == sec["total"] == 3
        assert sec["cached"] == 0
        assert body["cachedFiles"] == 0
        assert body["changedFiles"] == body["projectFiles"] == 3

    def test_unknown_dimension_filtered_out(self, client, tmp_path):
        self._setup_project(tmp_path)
        resp = client.get(
            "/api/projects/my-proj/estimates?dimensions=security,not-a-dim"
        )
        assert resp.status_code == 200
        assert set(resp.get_json()["dimensions"].keys()) == {"security"}

    def test_only_unknown_dimensions_returns_empty(self, client, tmp_path):
        self._setup_project(tmp_path)
        resp = client.get("/api/projects/my-proj/estimates?dimensions=not-a-dim")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["dimensions"] == {}
        assert body["projectFiles"] == 0

    def test_never_scanned_project_returns_zeros(self, client, tmp_path):
        # Project dir exists but has no repository_info.json — must not 500.
        (tmp_path / "bare-proj").mkdir()
        resp = client.get("/api/projects/bare-proj/estimates")
        assert resp.status_code == 200
        assert resp.get_json() == {
            "dimensions": {}, "projectFiles": 0, "cachedFiles": 0, "changedFiles": 0,
        }

    def test_missing_source_path_returns_zeros(self, client, tmp_path):
        proj_dir = tmp_path / "gone-proj"
        proj_dir.mkdir()
        (proj_dir / "repository_info.json").write_text(
            json.dumps({"location": "local", "path": str(tmp_path / "vanished")})
        )
        resp = client.get("/api/projects/gone-proj/estimates")
        assert resp.status_code == 200
        assert resp.get_json()["projectFiles"] == 0
