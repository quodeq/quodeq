"""Project threshold overrides fold into the standards fingerprint.

``_hash_standards`` hashes the compiled standards JSON, which is shared
across projects and does NOT change when a project tunes a numeric
threshold via ``.quodeq/standards-overrides.json``. Without folding the
overrides in, tuning ``max_lines`` 50 -> 60 and re-running reuses cached
findings classified under the 50-line rule with no drift signal.

The contract:

1. **Override change changes the fingerprint** — cached findings produced
   under the old threshold become detectable as drifted.
2. **Absent overrides leave the fingerprint byte-identical** to the
   pre-override-aware hash, so existing cache entries written before this
   feature (or by projects that never override) stay quiet — no phantom
   "standards changed" drift.
3. **Only the resolved content matters** — a formatting-only rewrite or a
   malformed file (which analysis ignores) must not shift the hash.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis import fingerprint
from quodeq.core.standards.overrides import OVERRIDES_RELPATH

DIM = "maintainability"


def _write_compiled_standard(standards_dir: Path, dimension: str, body: str) -> None:
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dimension}.json").write_text(body)


def _write_overrides(project_root: Path, text: str) -> None:
    path = project_root / OVERRIDES_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture(autouse=True)
def _clear_fingerprint_caches():
    fingerprint._hash_standards.cache_clear()
    yield
    fingerprint._hash_standards.cache_clear()


@pytest.fixture
def standards_dir(tmp_path: Path) -> Path:
    std = tmp_path / "standards"
    _write_compiled_standard(std, DIM, '{"rule": "v1"}')
    return std


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


def test_changing_override_value_changes_fingerprint(standards_dir, project_root):
    _write_overrides(
        project_root,
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 50}}}',
    )
    before = fingerprint._hash_standards(standards_dir, DIM, project_root)

    _write_overrides(
        project_root,
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 600}}}',
    )
    after = fingerprint._hash_standards(standards_dir, DIM, project_root)

    assert before is not None and after is not None
    assert before != after


def test_overrides_presence_changes_fingerprint_vs_baseline(standards_dir, project_root):
    baseline = fingerprint._hash_standards(standards_dir, DIM)
    _write_overrides(
        project_root,
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}',
    )
    overridden = fingerprint._hash_standards(standards_dir, DIM, project_root)

    assert baseline is not None and overridden is not None
    assert overridden != baseline


def test_absent_overrides_file_leaves_fingerprint_unchanged(standards_dir, project_root):
    # Load-bearing backward compatibility: entries written before the
    # override-aware hash carry the plain compiled-JSON hash. A project
    # with no overrides file must keep producing that exact value.
    baseline = fingerprint._hash_standards(standards_dir, DIM)
    with_root = fingerprint._hash_standards(standards_dir, DIM, project_root)
    assert with_root == baseline


def test_unchanged_overrides_file_keeps_fingerprint_stable(standards_dir, project_root):
    _write_overrides(
        project_root,
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}',
    )
    first = fingerprint._hash_standards(standards_dir, DIM, project_root)
    second = fingerprint._hash_standards(standards_dir, DIM, project_root)
    assert first == second


def test_formatting_only_rewrite_keeps_fingerprint(standards_dir, project_root):
    # The hash covers the resolved override mapping, not raw bytes —
    # re-saving the file with different whitespace/key order is not a
    # threshold change and must not flag drift.
    _write_overrides(
        project_root,
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}',
    )
    before = fingerprint._hash_standards(standards_dir, DIM, project_root)

    reordered = json.dumps(
        {"overrides": {"M-ANA-2": {"max_lines": 60}}, "version": 1}, indent=4,
    )
    _write_overrides(project_root, reordered)
    after = fingerprint._hash_standards(standards_dir, DIM, project_root)

    assert after == before


def test_malformed_overrides_treated_as_absent(standards_dir, project_root):
    # Analysis ignores a malformed file (load_project_overrides -> {});
    # the fingerprint must agree with what analysis actually uses.
    baseline = fingerprint._hash_standards(standards_dir, DIM)
    _write_overrides(project_root, "{not json")
    assert fingerprint._hash_standards(standards_dir, DIM, project_root) == baseline


def test_missing_compiled_standard_still_none(tmp_path: Path, project_root):
    _write_overrides(
        project_root,
        '{"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}',
    )
    assert fingerprint._hash_standards(tmp_path / "nostd", DIM, project_root) is None
