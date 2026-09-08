"""Subproject discovery walks breadth-first and stops at ``max_depth``.

``_iter_subproject_roots`` feeds ``detect_matches_recursive``: the repo root
comes first and shallower roots precede deeper ones, so the ``(rel_path,
matches)`` output stays stable across runs. Pinned here because the traversal
queue is a hot path on wide trees and its data structure has been swapped.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.config._discipline_detection import DisciplineRegistry
from quodeq.config._discipline_rule import DisciplineRule


def _registry() -> DisciplineRegistry:
    rule = DisciplineRule(name="python", detect_files=("pyproject.toml",))
    return DisciplineRegistry({rule.name: rule})


def _touch_manifest(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "pyproject.toml").write_text("[project]\nname = 'x'\n")


def _rels(repo: Path, roots: list[Path]) -> list[str]:
    return ["." if r == repo else r.relative_to(repo).as_posix() for r in roots]


def test_roots_come_back_breadth_first(tmp_path: Path):
    for rel in ("a", "b", "a/deep", "b/deeper/most"):
        _touch_manifest(tmp_path / rel)
    rels = _rels(tmp_path, _registry()._iter_subproject_roots(tmp_path, max_depth=4))
    assert rels[0] == "."
    assert sorted(rels[1:3]) == ["a", "b"]  # iterdir order is not stable
    assert rels[3:] == ["a/deep", "b/deeper/most"]


def test_max_depth_bounds_the_walk(tmp_path: Path):
    _touch_manifest(tmp_path / "a" / "deep")
    registry = _registry()
    assert _rels(tmp_path, registry._iter_subproject_roots(tmp_path, max_depth=1)) == ["."]
    assert _rels(tmp_path, registry._iter_subproject_roots(tmp_path, max_depth=2)) == [".", "a/deep"]
