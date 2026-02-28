from pathlib import Path

from codecompass.paths import is_subpath, resolve_path


def test_resolve_path_returns_absolute(tmp_path: Path):
    target = tmp_path / "reports"
    target.mkdir()
    resolved = resolve_path(str(target))
    assert resolved.is_absolute()
    assert resolved == target


def test_is_subpath_true(tmp_path: Path):
    parent_dir = tmp_path / "parent"
    child_dir = parent_dir / "child"
    parent_dir.mkdir()
    child_dir.mkdir()
    assert is_subpath(str(parent_dir), str(child_dir))


def test_is_subpath_false(tmp_path: Path):
    unrelated_dir1 = tmp_path / "unrelated1"
    unrelated_dir2 = tmp_path / "unrelated2"
    unrelated_dir1.mkdir()
    unrelated_dir2.mkdir()
    assert not is_subpath(str(unrelated_dir1), str(unrelated_dir2))
