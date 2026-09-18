"""Tests for _fs_projects.py: update_project_path and delete_project."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from quodeq.services._fs_projects import (
    update_project_path,
    delete_project,
)


# ---------------------------------------------------------------------------
# update_project_path
# ---------------------------------------------------------------------------


class TestUpdateProjectPath:
    def _setup_project(self, tmp_path: Path, info: dict | None = None):
        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        proj.mkdir(parents=True)
        data = info or {"name": "test", "path": "/old/path", "location": "local"}
        (proj / "repository_info.json").write_text(json.dumps(data))
        return str(reports), "proj-uuid"

    def test_update_local_path(self, tmp_path: Path):
        reports_dir, project = self._setup_project(tmp_path)
        new_dir = tmp_path / "new_repo"
        new_dir.mkdir()
        result = update_project_path(reports_dir, project, str(new_dir))
        assert result is True
        info = json.loads((Path(reports_dir) / project / "repository_info.json").read_text())
        assert info["path"] == str(new_dir.resolve())
        assert info["location"] == "local"

    @patch("quodeq.services._fs_projects.is_valid_repo_url", return_value=True)
    def test_update_url_path(self, mock_valid, tmp_path: Path):
        reports_dir, project = self._setup_project(tmp_path)
        result = update_project_path(reports_dir, project, "https://github.com/org/repo.git")
        assert result is True
        info = json.loads((Path(reports_dir) / project / "repository_info.json").read_text())
        assert info["location"] == "online"

    @patch("quodeq.services._fs_projects.is_valid_repo_url", return_value=False)
    def test_rejects_invalid_url(self, mock_valid, tmp_path: Path):
        reports_dir, project = self._setup_project(tmp_path)
        assert update_project_path(reports_dir, project, "https://bad") is False

    def test_rejects_path_traversal(self, tmp_path: Path):
        reports_dir, project = self._setup_project(tmp_path)
        assert update_project_path(reports_dir, project, "/tmp/../etc/passwd") is False

    def test_rejects_nonexistent_dir(self, tmp_path: Path):
        reports_dir, project = self._setup_project(tmp_path)
        assert update_project_path(reports_dir, project, "/nonexistent/path") is False

    def test_rejects_missing_info_file(self, tmp_path: Path):
        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        proj.mkdir(parents=True)
        # No repository_info.json
        assert update_project_path(str(reports), "proj-uuid", str(tmp_path)) is False

    def test_rejects_traversal_outside_reports(self, tmp_path: Path):
        reports = tmp_path / "reports"
        reports.mkdir()
        # Try to escape reports dir
        assert update_project_path(str(reports), "../escape", str(tmp_path)) is False


# ---------------------------------------------------------------------------
# delete_project
# ---------------------------------------------------------------------------


class TestDeleteProject:
    def test_delete_simple_project(self, tmp_path: Path):
        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        proj.mkdir(parents=True)
        (proj / "data.json").write_text("{}")
        assert delete_project(str(reports), "proj-uuid") is True
        assert not proj.exists()

    def test_delete_nonexistent(self, tmp_path: Path):
        reports = tmp_path / "reports"
        reports.mkdir()
        assert delete_project(str(reports), "nope") is False

    def test_cascade_deletes_children(self, tmp_path: Path):
        reports = tmp_path / "reports"
        parent = reports / "parent-uuid"
        child = reports / "child-uuid"
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (child / "repository_info.json").write_text(json.dumps({"parent": "parent-uuid"}))
        assert delete_project(str(reports), "parent-uuid") is True
        assert not parent.exists()
        assert not child.exists()

    def test_rejects_traversal(self, tmp_path: Path):
        reports = tmp_path / "reports"
        reports.mkdir()
        assert delete_project(str(reports), "../escape") is False
