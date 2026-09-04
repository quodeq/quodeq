"""Tests for cascade delete of parent projects."""

from __future__ import annotations

import json
from pathlib import Path

import quodeq.services._fs_projects as fs_projects
from quodeq.services._fs_projects import delete_project
from quodeq.services._repo_index import _load_repo_index, add_repo_index_entry


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


def test_delete_parent_purges_index_entries_for_parent_and_children(tmp_path: Path) -> None:
    """A stale index entry pointing at a deleted uuid would let
    find_existing_project wrongly report a "duplicate" for a repo identity
    that's actually free again -- deletion must purge it."""
    parent_id = "parent-uuid"
    child_id = "child-uuid"
    other_id = "unrelated-uuid"
    _make_project(tmp_path, parent_id)
    _make_project(tmp_path, child_id, parent=parent_id)
    _make_project(tmp_path, other_id)

    add_repo_index_entry(tmp_path, "parent", "/repo/parent", None, parent_id)
    add_repo_index_entry(tmp_path, "parent", "/repo/parent", "sub", child_id)
    add_repo_index_entry(tmp_path, "other", "/repo/other", None, other_id)

    result = delete_project(str(tmp_path), parent_id)

    assert result is True
    remaining = _load_repo_index(tmp_path)
    assert set(remaining.values()) == {other_id}


def test_delete_purges_child_index_entries_even_when_parent_removal_fails(
    tmp_path: Path, monkeypatch,
) -> None:
    """Regression: a plausible filesystem race (e.g. a lock only on the
    top-level dir) can remove a child successfully but then fail to remove
    the parent directory. The child's index entry must still be purged --
    otherwise a later find_existing_project lookup for that now-freed
    identity hits a stale entry pointing at a nonexistent uuid. The parent's
    own entry must NOT be purged: its directory still exists."""
    parent_id = "parent-uuid"
    child_id = "child-uuid"
    _make_project(tmp_path, parent_id)
    _make_project(tmp_path, child_id, parent=parent_id)

    add_repo_index_entry(tmp_path, "parent", "/repo/parent", None, parent_id)
    add_repo_index_entry(tmp_path, "parent", "/repo/parent", "sub", child_id)

    real_remove = fs_projects.remove_project_dir

    def _fail_only_for_parent(path: Path) -> bool:
        if path.name == parent_id:
            return False
        return real_remove(path)

    monkeypatch.setattr(fs_projects, "remove_project_dir", _fail_only_for_parent)

    result = delete_project(str(tmp_path), parent_id)

    assert result is False
    assert not (tmp_path / child_id).exists()
    assert (tmp_path / parent_id).exists()

    remaining = _load_repo_index(tmp_path)
    assert set(remaining.values()) == {parent_id}
