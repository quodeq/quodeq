"""Pruning behavior for ``_has_required_files``.

The detect_requires_file gate uses ``**/*`` patterns that traditionally went
through ``Path.glob``, which scandirs into ``build/``/``.gradle/``/``.git/``
before the in-loop skip-dir filter could discard the match. On large
multi-module repos this turned a millisecond gate into multi-second walks.

These tests pin two things:

1. **Semantic parity** — the gate's True/False answer is unchanged for
   patterns under skip dirs vs. under regular source dirs.
2. **Pruning at the directory level** — when looking for ``**/*.kt`` the
   implementation must not ``scandir`` into ``_SUBPROJECT_SKIP_DIRS`` or
   hidden directories. Without pruning, the wallclock blows up.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.config._discipline_detection import (
    _SUBPROJECT_SKIP_DIRS,
    DisciplineRegistry,
)
from quodeq.config._discipline_rule import DisciplineRule


def _registry(rule: DisciplineRule) -> DisciplineRegistry:
    return DisciplineRegistry({rule.name: rule})


def _kotlin_rule() -> DisciplineRule:
    """Mirror the real ``mobile_kotlin`` rule's gating pattern."""
    return DisciplineRule(
        name="mobile_kotlin",
        detect_files=("build.gradle.kts",),
        detect_requires_file="**/*.kt",
    )


def test_returns_true_for_match_outside_skip_dirs(tmp_path: Path):
    """Baseline: a regular Foo.kt under src/ satisfies the gate."""
    (tmp_path / "src" / "main" / "kotlin").mkdir(parents=True)
    (tmp_path / "src" / "main" / "kotlin" / "Foo.kt").write_text("")
    (tmp_path / "build.gradle.kts").write_text("")

    reg = _registry(_kotlin_rule())
    assert reg._has_required_files(tmp_path, _kotlin_rule()) is True


def test_returns_false_when_match_only_in_skip_dir(tmp_path: Path):
    """A .kt only under build/ does NOT satisfy the gate. Mirrors today's
    semantics — vendored / generated copies don't count as project content.
    """
    (tmp_path / "build" / "generated").mkdir(parents=True)
    (tmp_path / "build" / "generated" / "Generated.kt").write_text("")

    reg = _registry(_kotlin_rule())
    assert reg._has_required_files(tmp_path, _kotlin_rule()) is False


def test_returns_false_when_match_only_in_hidden_dir(tmp_path: Path):
    """A .kt only under .gradle/ does NOT satisfy the gate."""
    (tmp_path / ".gradle" / "caches").mkdir(parents=True)
    (tmp_path / ".gradle" / "caches" / "Cached.kt").write_text("")

    reg = _registry(_kotlin_rule())
    assert reg._has_required_files(tmp_path, _kotlin_rule()) is False


def test_returns_true_for_match_at_root(tmp_path: Path):
    """A .kt directly in the repo root counts."""
    (tmp_path / "Foo.kt").write_text("")

    reg = _registry(_kotlin_rule())
    assert reg._has_required_files(tmp_path, _kotlin_rule()) is True


def test_rule_without_detect_requires_file_returns_true(tmp_path: Path):
    """When no gate is set, the rule trivially passes (semantic-preserving)."""
    rule = DisciplineRule(name="anything", detect_requires_file=None)
    reg = _registry(rule)
    assert reg._has_required_files(tmp_path, rule) is True


def test_does_not_scandir_into_skip_dirs(tmp_path: Path):
    """Pruning happens at the directory level: ``scandir`` is never called
    on ``build/`` or ``.gradle/`` while looking for ``**/*.kt``.

    Without pruning, ``Path.glob`` enumerates *all* matches before the
    in-loop filter discards skip-dir hits; on a real Android repo that
    means scandir gets called ~2M times. This test pins the pruning so a
    regression here would surface immediately.

    Topology is chosen so the only valid match lives behind directories
    alphabetically *after* the skip dirs, forcing any non-pruning glob
    implementation to scandir the skip dirs before finding it.
    """
    # 'build' (skip) and '.gradle' (hidden) sort before 'src' in directory
    # listings on every filesystem we care about, so a non-pruning glob
    # implementation will scandir them before reaching src/main/kotlin/.
    (tmp_path / "build").mkdir()
    for i in range(5):
        (tmp_path / "build" / f"Generated{i}.kt").write_text("")
    (tmp_path / ".gradle" / "caches").mkdir(parents=True)
    for i in range(5):
        (tmp_path / ".gradle" / "caches" / f"Cached{i}.kt").write_text("")
    (tmp_path / "src" / "main" / "kotlin").mkdir(parents=True)
    (tmp_path / "src" / "main" / "kotlin" / "Foo.kt").write_text("")

    scandir_calls: list[str] = []
    real_scandir = os.scandir

    def tracking_scandir(path):
        scandir_calls.append(os.fspath(path))
        return real_scandir(path)

    with patch("os.scandir", side_effect=tracking_scandir):
        reg = _registry(_kotlin_rule())
        assert reg._has_required_files(tmp_path, _kotlin_rule()) is True

    descended_paths = [Path(p).resolve() for p in scandir_calls]
    build_dir = (tmp_path / "build").resolve()
    gradle_dir = (tmp_path / ".gradle").resolve()
    assert build_dir not in descended_paths, (
        f"scandir descended into {build_dir} despite skip-dir membership; "
        f"calls were: {scandir_calls}"
    )
    assert gradle_dir not in descended_paths, (
        f"scandir descended into {gradle_dir} despite hidden-dir status; "
        f"calls were: {scandir_calls}"
    )


def test_non_recursive_pattern_still_works(tmp_path: Path):
    """``detect_requires_file='lib/*.sh'`` (non-recursive) must keep working.

    The fix only changes the recursive branch; single-level patterns still
    need to match files in the named subdirectory.
    """
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "deploy.sh").write_text("")
    rule = DisciplineRule(name="shell", detect_requires_file="lib/*.sh")

    reg = _registry(rule)
    assert reg._has_required_files(tmp_path, rule) is True


def test_non_recursive_pattern_returns_false_when_no_match(tmp_path: Path):
    """Non-recursive pattern with no match returns False."""
    (tmp_path / "lib").mkdir()
    rule = DisciplineRule(name="shell", detect_requires_file="lib/*.sh")

    reg = _registry(rule)
    assert reg._has_required_files(tmp_path, rule) is False


def test_pruning_covers_every_skip_dir(tmp_path: Path):
    """Every name in ``_SUBPROJECT_SKIP_DIRS`` must be pruned, not just
    the well-known Kotlin/Android ones. Catches drift where the list grows
    but the implementation forgets to honor an entry.
    """
    # Put a .kt in every skip dir. No legitimate match elsewhere — so the
    # gate's correct answer is False, and an implementation that fails to
    # prune even one skip dir would return True instead.
    for name in _SUBPROJECT_SKIP_DIRS:
        d = tmp_path / name
        d.mkdir()
        (d / "Inside.kt").write_text("")

    reg = _registry(_kotlin_rule())
    assert reg._has_required_files(tmp_path, _kotlin_rule()) is False
