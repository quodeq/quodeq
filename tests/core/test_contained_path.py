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

from quodeq.core.utils.io import contained_path, resolve_child_dir


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


# --- resolve_child_dir: resolution by listing, not by joining ---------------


def test_resolve_child_dir_returns_a_real_child(tmp_path: Path) -> None:
    (tmp_path / "project-a").mkdir()
    assert resolve_child_dir(tmp_path, "project-a") == str(tmp_path / "project-a")


def test_resolve_child_dir_returns_none_for_a_missing_child(tmp_path: Path) -> None:
    assert resolve_child_dir(tmp_path, "nope") is None


def test_resolve_child_dir_ignores_files(tmp_path: Path) -> None:
    (tmp_path / "notadir").write_text("x")
    assert resolve_child_dir(tmp_path, "notadir") is None


@pytest.mark.parametrize(
    "hostile",
    ["..", "../..", "../outside", "/etc", "/etc/passwd", "..\\..", "a/../b", ""],
)
def test_resolve_child_dir_matches_nothing_hostile(tmp_path: Path, hostile: str) -> None:
    """Traversal values are not rejected, they simply match no entry.

    This is the property that makes listing-based resolution better than a
    containment check: there is no guard to get wrong, because the caller's
    string is only ever compared against names that already exist.
    """
    (tmp_path / "real").mkdir()
    (tmp_path.parent / "outside").mkdir(exist_ok=True)
    assert resolve_child_dir(tmp_path, hostile) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_resolve_child_dir_refuses_a_symlink_even_to_a_real_directory(tmp_path: Path) -> None:
    """Symlinks never resolve, whether they escape the root or not.

    ``os.scandir`` entries report is_dir() as True for a link to a directory
    by default, which would hand back root/escape and let the caller walk
    straight out of the tree. The resolver asks for follow_symlinks=False.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    real = root / "real"
    real.mkdir()
    (root / "escape").symlink_to(outside)
    (root / "inside-link").symlink_to(real)

    assert resolve_child_dir(root, "escape") is None
    assert resolve_child_dir(root, "inside-link") is None
    assert resolve_child_dir(root, "real") == str(root / "real")


def test_resolve_child_dir_on_a_missing_root_is_none(tmp_path: Path) -> None:
    assert resolve_child_dir(tmp_path / "no-such-root", "anything") is None
