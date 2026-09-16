"""is_within: the containment predicate behind the services path jails."""
from __future__ import annotations

from quodeq.core.utils.io import is_within


def test_child_and_self_are_within(tmp_path):
    (tmp_path / "a").mkdir()
    assert is_within(tmp_path / "a", tmp_path)
    assert is_within(tmp_path, tmp_path)


def test_escapes_are_not_within(tmp_path):
    assert not is_within(tmp_path / ".." / "elsewhere", tmp_path)
    assert not is_within(tmp_path.parent, tmp_path)


def test_sibling_with_common_prefix_is_not_within(tmp_path):
    sibling = tmp_path.parent / f"{tmp_path.name}-sibling"
    sibling.mkdir()
    assert not is_within(sibling, tmp_path)


def test_symlink_out_of_root_is_rejected(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside)
    assert not is_within(link, tmp_path)


def test_missing_paths_do_not_raise(tmp_path):
    assert is_within(tmp_path / "does-not-exist", tmp_path)
