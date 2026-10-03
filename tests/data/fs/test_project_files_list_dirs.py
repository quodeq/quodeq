"""Names of the project directories directly under a reports root, used by
registration rollback to snapshot/diff instead of walking the filesystem itself.
"""
from __future__ import annotations

from quodeq.data.fs.project_files import list_project_dirs


def test_lists_child_dirs_only(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "f.txt").write_text("x")
    assert list_project_dirs(tmp_path) == {"a", "b"}


def test_missing_root_is_empty(tmp_path):
    assert list_project_dirs(tmp_path / "nope") == set()
