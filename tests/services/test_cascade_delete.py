"""Tests for cascade delete of parent projects."""

from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._fs_projects import delete_project


def _make_project(reports_root: Path, name: str, parent: str | None = None) -> Path:
    """Create a minimal project directory with repository_info.json."""
    project_dir = reports_root / name
    project_dir.mkdir(parents=True, exist_ok=True)
    info: dict = {"name": name}
    if parent is not None:
        info["parent"] = parent
    (project_dir / "repository_info.json").write_text(json.dumps(info))
    return project_dir


def test_delete_parent_removes_children(tmp_path: Path) -> None:
    parent_id = "parent-uuid"
    child1_id = "child-uuid-1"
    child2_id = "child-uuid-2"

    _make_project(tmp_path, parent_id)
    _make_project(tmp_path, child1_id, parent=parent_id)
    _make_project(tmp_path, child2_id, parent=parent_id)

    result = delete_project(str(tmp_path), parent_id)

    assert result is True
    assert not (tmp_path / parent_id).exists()
    assert not (tmp_path / child1_id).exists()
    assert not (tmp_path / child2_id).exists()


def test_delete_child_leaves_parent(tmp_path: Path) -> None:
    parent_id = "parent-uuid"
    child_id = "child-uuid"

    _make_project(tmp_path, parent_id)
    _make_project(tmp_path, child_id, parent=parent_id)

    result = delete_project(str(tmp_path), child_id)

    assert result is True
    assert not (tmp_path / child_id).exists()
    assert (tmp_path / parent_id).exists()


def test_delete_project_without_children(tmp_path: Path) -> None:
    project_id = "standalone-uuid"
    _make_project(tmp_path, project_id)

    result = delete_project(str(tmp_path), project_id)

    assert result is True
    assert not (tmp_path / project_id).exists()
