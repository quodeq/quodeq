"""Tests for data.fs.project_resolver — UUID-based project identity resolution."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.data.fs.project_resolver import (
    ProjectIdentity,
    clear_index_cache,
    resolve_project_uuid,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_index_cache()
    yield
    clear_index_cache()


class TestResolveProjectUuid:
    def test_local_project_creates_directory(self, tmp_path):
        identity = ProjectIdentity(
            project_name="my-project",
            repo_path=str(tmp_path / "repo"),
            discipline="python",
            location="local",
        )
        (tmp_path / "repo").mkdir()
        uuid_str = resolve_project_uuid(tmp_path / "reports", identity)
        assert uuid_str
        project_dir = tmp_path / "reports" / uuid_str
        assert project_dir.is_dir()
        info = json.loads((project_dir / "repository_info.json").read_text())
        assert info["name"] == "my-project"
        assert info["discipline"] == "python"
        assert info["location"] == "local"

    def test_online_project_preserves_url(self, tmp_path):
        identity = ProjectIdentity(
            project_name="remote-repo",
            repo_path="https://github.com/org/repo",
            discipline=None,
            location="online",
        )
        uuid_str = resolve_project_uuid(tmp_path / "reports", identity)
        info = json.loads((tmp_path / "reports" / uuid_str / "repository_info.json").read_text())
        assert info["path"] == "https://github.com/org/repo"

    def test_idempotent_resolution(self, tmp_path):
        reports = tmp_path / "reports"
        identity = ProjectIdentity(
            project_name="my-project",
            repo_path=str(tmp_path / "repo"),
            discipline="python",
            location="local",
        )
        (tmp_path / "repo").mkdir()
        uuid1 = resolve_project_uuid(reports, identity)
        clear_index_cache()
        uuid2 = resolve_project_uuid(reports, identity)
        assert uuid1 == uuid2

    def test_creates_reports_dir_if_missing(self, tmp_path):
        reports = tmp_path / "non" / "existent" / "reports"
        identity = ProjectIdentity(
            project_name="test",
            repo_path=str(tmp_path),
            discipline=None,
            location="local",
        )
        uuid_str = resolve_project_uuid(reports, identity)
        assert reports.is_dir()
        assert uuid_str

    def test_scoped_project_creates_parent_and_child(self, tmp_path):
        reports = tmp_path / "reports"
        identity = ProjectIdentity(
            project_name="mono-repo",
            repo_path=str(tmp_path / "repo"),
            discipline="python",
            location="local",
            scope_path="packages/core",
        )
        (tmp_path / "repo").mkdir()
        uuid_str = resolve_project_uuid(reports, identity)
        info = json.loads((reports / uuid_str / "repository_info.json").read_text())
        assert info["name"] == "mono-repo/packages/core"
        assert info["scopePath"] == "packages/core"
        assert "parent" in info

    def test_scoped_project_idempotent(self, tmp_path):
        reports = tmp_path / "reports"
        (tmp_path / "repo").mkdir()
        identity = ProjectIdentity(
            project_name="mono",
            repo_path=str(tmp_path / "repo"),
            discipline=None,
            location="local",
            scope_path="sub",
        )
        uuid1 = resolve_project_uuid(reports, identity)
        clear_index_cache()
        uuid2 = resolve_project_uuid(reports, identity)
        assert uuid1 == uuid2

    def test_custom_repository_backend(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        index_store: dict = {}

        class FakeRepo:
            def load_index(self, reports_dir):
                return dict(index_store)
            def save_index(self, reports_dir, index):
                index_store.clear()
                index_store.update(index)

        identity = ProjectIdentity(
            project_name="test",
            repo_path=str(tmp_path),
            discipline=None,
            location="local",
        )
        repo = FakeRepo()
        uuid_str = resolve_project_uuid(reports, identity, repository=repo)
        assert uuid_str
        assert len(index_store) == 1

    @patch("quodeq.data.fs.project_resolver._find_existing_project", return_value="existing-uuid")
    @patch("quodeq.data.fs.project_resolver.find_children", return_value=[])
    def test_unscoped_existing_no_children(self, mock_children, mock_find, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        (reports / "existing-uuid").mkdir()
        identity = ProjectIdentity(
            project_name="test",
            repo_path=str(tmp_path),
            discipline=None,
            location="local",
        )
        uuid_str = resolve_project_uuid(reports, identity)
        assert uuid_str == "existing-uuid"

    @patch("quodeq.data.fs.project_resolver._create_project", return_value="dot-uuid")
    @patch("quodeq.data.fs.project_resolver._find_existing_project")
    @patch("quodeq.data.fs.project_resolver.find_children", return_value=["child-1"])
    def test_unscoped_existing_with_children_creates_dot(self, mock_children, mock_find, mock_create, tmp_path):
        """When an unscoped project has children, a dot-scoped project is created."""
        reports = tmp_path / "reports"
        reports.mkdir()
        # First call finds existing, second call (for dot identity) returns None
        mock_find.side_effect = ["existing-uuid", None]
        identity = ProjectIdentity(
            project_name="test",
            repo_path=str(tmp_path),
            discipline=None,
            location="local",
        )
        uuid_str = resolve_project_uuid(reports, identity)
        assert uuid_str == "dot-uuid"

    @patch("quodeq.data.fs.project_resolver._find_existing_project")
    @patch("quodeq.data.fs.project_resolver.find_children", return_value=["child-1"])
    def test_unscoped_existing_with_children_returns_existing_dot(self, mock_children, mock_find, tmp_path):
        """When dot project already exists, return it."""
        reports = tmp_path / "reports"
        reports.mkdir()
        mock_find.side_effect = ["existing-uuid", "dot-existing-uuid"]
        identity = ProjectIdentity(
            project_name="test",
            repo_path=str(tmp_path),
            discipline=None,
            location="local",
        )
        uuid_str = resolve_project_uuid(reports, identity)
        assert uuid_str == "dot-existing-uuid"
