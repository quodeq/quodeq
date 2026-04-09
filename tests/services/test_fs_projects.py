"""Tests for _fs_projects.py — project listing, path updates, deletion."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from quodeq.services._fs_projects import (
    find_children,
    _build_parent_child_sets,
    update_project_path,
    delete_project,
    get_project_info,
)


# ---------------------------------------------------------------------------
# find_children
# ---------------------------------------------------------------------------


class TestFindChildren:
    def test_finds_children(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        child = tmp_path / "child-uuid"
        child.mkdir()
        (child / "repository_info.json").write_text(json.dumps({"parent": "parent-uuid"}))
        # Unrelated project
        other = tmp_path / "other-uuid"
        other.mkdir()
        (other / "repository_info.json").write_text(json.dumps({"parent": "someone-else"}))

        result = find_children(tmp_path, "parent-uuid")
        assert result == ["child-uuid"]

    def test_no_children(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        assert find_children(tmp_path, "parent-uuid") == []

    def test_skips_corrupt_json(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        child = tmp_path / "child-uuid"
        child.mkdir()
        (child / "repository_info.json").write_text("not json")
        assert find_children(tmp_path, "parent-uuid") == []

    def test_skips_missing_info(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        child = tmp_path / "child-uuid"
        child.mkdir()
        # No repository_info.json
        assert find_children(tmp_path, "parent-uuid") == []


# ---------------------------------------------------------------------------
# _build_parent_child_sets
# ---------------------------------------------------------------------------


class TestBuildParentChildSets:
    def test_identifies_parents_and_children(self, tmp_path: Path):
        (tmp_path / "child1").mkdir()
        (tmp_path / "child1" / "repository_info.json").write_text(
            json.dumps({"parent": "parent-uuid"})
        )
        (tmp_path / "standalone").mkdir()
        (tmp_path / "standalone" / "repository_info.json").write_text(
            json.dumps({"name": "standalone"})
        )
        parents, subs = _build_parent_child_sets(tmp_path, ["child1", "standalone"])
        assert parents == {"parent-uuid"}
        assert subs == {"child1"}

    def test_empty_dirs(self, tmp_path: Path):
        parents, subs = _build_parent_child_sets(tmp_path, [])
        assert parents == set()
        assert subs == set()

    def test_corrupt_json_skipped(self, tmp_path: Path):
        (tmp_path / "bad").mkdir()
        (tmp_path / "bad" / "repository_info.json").write_text("{{{")
        parents, subs = _build_parent_child_sets(tmp_path, ["bad"])
        assert parents == set()
        assert subs == set()


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

    @patch("quodeq.shared.repo_handler.is_valid_repo_url", return_value=True)
    def test_update_url_path(self, mock_valid, tmp_path: Path):
        reports_dir, project = self._setup_project(tmp_path)
        result = update_project_path(reports_dir, project, "https://github.com/org/repo.git")
        assert result is True
        info = json.loads((Path(reports_dir) / project / "repository_info.json").read_text())
        assert info["location"] == "online"

    @patch("quodeq.shared.repo_handler.is_valid_repo_url", return_value=False)
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


# ---------------------------------------------------------------------------
# get_project_info
# ---------------------------------------------------------------------------


class TestGetProjectInfo:
    def test_returns_info(self, tmp_path: Path):
        proj = tmp_path / "proj-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text(json.dumps({
            "name": "test",
            "discipline": "software",
            "location": "local",
            "path": str(tmp_path),
        }))
        with patch("quodeq.services._fs_projects._list_available_dimensions_for_discipline", return_value=["sec"]):
            with patch("quodeq.services._fs_projects._has_fingerprints", return_value=False):
                result = get_project_info(str(tmp_path), "proj-uuid")
        assert result is not None
        assert result["name"] == "test"
        assert result["discipline"] == "software"
        assert result["availableDimensions"] == ["sec"]
        assert result["hasFingerprints"] is False

    def test_returns_none_for_missing(self, tmp_path: Path):
        assert get_project_info(str(tmp_path), "nope") is None

    def test_returns_none_for_corrupt_json(self, tmp_path: Path):
        proj = tmp_path / "proj-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text("not json")
        assert get_project_info(str(tmp_path), "proj-uuid") is None

    def test_path_missing_detection(self, tmp_path: Path):
        proj = tmp_path / "proj-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text(json.dumps({
            "name": "test",
            "location": "online",
            "path": "/local/path",  # Not a URL
        }))
        with patch("quodeq.services._fs_projects._list_available_dimensions_for_discipline", return_value=[]):
            with patch("quodeq.services._fs_projects._has_fingerprints", return_value=False):
                with patch("quodeq.services._fs_projects._infer_discipline", return_value=None):
                    result = get_project_info(str(tmp_path), "proj-uuid")
        assert result is not None
        assert result["pathMissing"] is True

    def test_traversal_rejected(self, tmp_path: Path):
        result = get_project_info(str(tmp_path), "../escape")
        assert result is None
