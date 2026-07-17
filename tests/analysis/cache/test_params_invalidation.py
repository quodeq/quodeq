"""Threshold override changes shift cache keys; reverting restores them.

End-to-end contract for the feature: an entry cached under default
thresholds is unreachable while a non-default override is in force for its
dimension, and reachable again the moment the override is removed. Other
dimensions never shift.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis import fingerprint
from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
from quodeq.core.standards.overrides import OVERRIDES_RELPATH

DIM = "maintainability"
OTHER_DIM = "standards"


@pytest.fixture(autouse=True)
def _clear_caches():
    fingerprint._hash_standards.cache_clear()
    yield
    fingerprint._hash_standards.cache_clear()


def _write_compiled(standards_dir: Path, dimension: str) -> None:
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dimension}.json").write_text(json.dumps({
        "id": dimension,
        "principles": [{"name": "P", "requirements": [{
            "id": f"{dimension[:1].upper()}-ANA-2", "text": "Max {max_lines} lines",
            "params": {"max_lines": {"default": 50, "min": 10, "max": 500}},
        }]}],
    }))


@pytest.fixture()
def config(tmp_path: Path) -> RunConfig:
    src = tmp_path / "repo"
    src.mkdir()
    (src / "auth.py").write_text("def f():\n    pass\n")
    standards_dir = tmp_path / "standards"
    _write_compiled(standards_dir, DIM)
    _write_compiled(standards_dir, OTHER_DIM)
    return RunConfig(src=src, language="python", standards_dir=standards_dir)


def _set_override(config: RunConfig, value: int | None) -> None:
    path = config.src / OVERRIDES_RELPATH
    if value is None:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"version": 1, "overrides": {"M-ANA-2": {"max_lines": value}}}))
    fingerprint._hash_standards.cache_clear()


def test_override_shifts_key_and_revert_restores_it(config: RunConfig):
    baseline = build_cache_key_for_file(config, "auth.py", DIM)

    _set_override(config, 60)
    overridden = build_cache_key_for_file(config, "auth.py", DIM)
    assert overridden != baseline

    _set_override(config, None)
    assert build_cache_key_for_file(config, "auth.py", DIM) == baseline


def test_override_equal_to_default_keeps_key(config: RunConfig):
    baseline = build_cache_key_for_file(config, "auth.py", DIM)
    _set_override(config, 50)
    assert build_cache_key_for_file(config, "auth.py", DIM) == baseline


def test_other_dimension_key_never_shifts(config: RunConfig):
    baseline_other = build_cache_key_for_file(config, "auth.py", OTHER_DIM)
    _set_override(config, 60)
    assert build_cache_key_for_file(config, "auth.py", OTHER_DIM) == baseline_other
