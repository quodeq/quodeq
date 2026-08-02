"""Containment guard behaviour for `contained_path`.

The shape of this helper is load-bearing (see its docstring): it must return
the safe path rather than only raising, and it must use realpath +
startswith so static analysers recognise it as a barrier. The last test in
this module pins the return-value contract, which is the part a well-meaning
"simplify this to a plain validator" refactor would otherwise delete.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from quodeq.core.utils.io import contained_path


def test_allows_direct_child(tmp_path: Path) -> None:
    child = tmp_path / "project-a"
    assert contained_path(child, tmp_path) == os.path.realpath(str(child))


def test_allows_nested_descendant(tmp_path: Path) -> None:
    nested = tmp_path / "project-a" / "run-1" / "findings.jsonl"
    assert contained_path(nested, tmp_path) == os.path.realpath(str(nested))


def test_allows_the_root_itself(tmp_path: Path) -> None:
    assert contained_path(tmp_path, tmp_path) == os.path.realpath(str(tmp_path))


def test_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes its root"):
        contained_path(tmp_path / ".." / "elsewhere", tmp_path)


def test_rejects_sibling_prefix_collision(tmp_path: Path) -> None:
    """`/root-evil` must not pass containment for root `/root`.

    A naive ``startswith(root)`` without the separator admits this.
    """
    root = tmp_path / "root"
    root.mkdir()
    sibling = tmp_path / "root-evil"
    sibling.mkdir()
    with pytest.raises(ValueError, match="escapes its root"):
        contained_path(sibling, root)


def test_rejects_absolute_path_outside_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes its root"):
        contained_path("/etc/passwd", tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_rejects_symlink_escaping_the_root(tmp_path: Path) -> None:
    """Containment is judged on the real target, not the link path."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes its root"):
        contained_path(root / "escape", root)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_returns_the_real_target_for_an_internal_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "real").mkdir(parents=True)
    (root / "link").symlink_to(root / "real")
    assert contained_path(root / "link", root) == os.path.realpath(str(root / "real"))


def test_returns_the_sanitised_value_not_none(tmp_path: Path) -> None:
    """The barrier contract: callers use the return value.

    A validator that returns ``None`` leaves the caller's own (tainted)
    variable flowing to the file sink, which is what made the previous
    ``validate_resolved_within`` useless as a barrier.
    """
    result = contained_path(tmp_path / "a" / ".." / "b", tmp_path)
    assert result is not None
    assert result == os.path.realpath(str(tmp_path / "b"))
