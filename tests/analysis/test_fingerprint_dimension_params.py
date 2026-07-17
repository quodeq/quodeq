"""Per-dimension params fingerprint — the cache-key input for thresholds.

Contract:
1. Defaults (no overrides file, or overrides equal to defaults) hash to ""
   so legacy cache keys stay byte-identical.
2. A non-default override yields a stable non-empty hash.
3. Reverting the override restores "".
4. An override in another dimension's requirement does not affect this
   dimension's hash.
5. effective_params always carries the full resolved values.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis import fingerprint
from quodeq.analysis.fingerprint import dimension_params_state
from quodeq.core.standards.overrides import OVERRIDES_RELPATH

DIM = "maintainability"


def _write_compiled(standards_dir: Path, dimension: str, req_id: str, default: int) -> None:
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dimension}.json").write_text(json.dumps({
        "id": dimension,
        "principles": [{"name": "P", "requirements": [{
            "id": req_id, "text": "Max {max_lines} lines",
            "params": {"max_lines": {"default": default, "min": 10, "max": 500}},
        }]}],
    }))


def _write_overrides(project_root: Path, overrides: dict) -> None:
    path = project_root / OVERRIDES_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "overrides": overrides}))


@pytest.fixture(autouse=True)
def _clear_caches():
    fingerprint._hash_standards.cache_clear()
    yield
    fingerprint._hash_standards.cache_clear()


@pytest.fixture()
def standards_dir(tmp_path: Path) -> Path:
    d = tmp_path / "standards"
    _write_compiled(d, DIM, "M-ANA-2", 50)
    return d


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_no_overrides_hashes_empty(standards_dir, project_root):
    params_hash, effective = dimension_params_state(standards_dir, DIM, project_root)
    assert params_hash == ""
    assert effective == {"M-ANA-2": {"max_lines": 50}}


def test_override_equal_to_default_hashes_empty(standards_dir, project_root):
    _write_overrides(project_root, {"M-ANA-2": {"max_lines": 50}})
    params_hash, _ = dimension_params_state(standards_dir, DIM, project_root)
    assert params_hash == ""


def test_non_default_override_hashes_non_empty_and_stable(standards_dir, project_root):
    _write_overrides(project_root, {"M-ANA-2": {"max_lines": 60}})
    h1, effective = dimension_params_state(standards_dir, DIM, project_root)
    h2, _ = dimension_params_state(standards_dir, DIM, project_root)
    assert h1 and h1 == h2
    assert effective == {"M-ANA-2": {"max_lines": 60}}


def test_revert_restores_empty_hash(standards_dir, project_root):
    _write_overrides(project_root, {"M-ANA-2": {"max_lines": 60}})
    assert dimension_params_state(standards_dir, DIM, project_root)[0] != ""
    (project_root / OVERRIDES_RELPATH).unlink()
    dimension_params_state.cache_clear()
    assert dimension_params_state(standards_dir, DIM, project_root)[0] == ""


def test_foreign_dimension_override_does_not_shift_hash(standards_dir, project_root):
    _write_compiled(standards_dir, "standards", "S-SEC-1", 3)
    _write_overrides(project_root, {"S-SEC-1": {"max_lines": 5}})
    assert dimension_params_state(standards_dir, DIM, project_root)[0] == ""


def test_missing_dimension_file_hashes_empty(standards_dir, project_root):
    params_hash, effective = dimension_params_state(standards_dir, "nonexistent", project_root)
    assert (params_hash, effective) == ("", {})


def test_none_standards_dir_hashes_empty(project_root):
    assert dimension_params_state(None, DIM, project_root) == ("", {})


def _write_compiled_raw_params(standards_dir: Path, dimension: str, req_id: str, params) -> None:
    """A compiled file whose ``params`` block has a shape ``effective_params``
    cannot handle: a spec that isn't a dict (e.g. a bare int), or a
    ``params`` value that isn't a mapping of name -> spec at all."""
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dimension}.json").write_text(json.dumps({
        "id": dimension,
        "principles": [{"name": "P", "requirements": [{
            "id": req_id, "text": "Max {max_lines} lines",
            "params": params,
        }]}],
    }))


def test_shape_invalid_param_spec_hashes_empty_without_raising(tmp_path, project_root):
    """``"params": {"max_lines": 5}`` -- the spec is a bare int, not a dict.

    ``effective_params`` calls ``spec.get("default")`` and would raise
    AttributeError. Keying must degrade to ("", {}), matching the
    missing-file/unparseable-JSON behavior, not propagate the exception.
    """
    bad_dir = tmp_path / "standards-bad-spec"
    _write_compiled_raw_params(bad_dir, DIM, "M-ANA-2", {"max_lines": 5})
    assert dimension_params_state(bad_dir, DIM, project_root) == ("", {})


def test_shape_invalid_params_list_hashes_empty_without_raising(tmp_path, project_root):
    """``"params": [...]`` -- not a mapping at all.

    ``dimension_params`` treats the list as truthy and calls
    ``effective_params``, which does ``(req.get("params") or {}).items()``
    and would raise AttributeError/TypeError on a list. Must degrade to
    ("", {}) rather than crash.
    """
    bad_dir = tmp_path / "standards-bad-list"
    _write_compiled_raw_params(bad_dir, DIM, "M-ANA-2", ["max_lines"])
    assert dimension_params_state(bad_dir, DIM, project_root) == ("", {})
