"""#1487 - load_evidence_map_from_db must use a single query (list_all).

The previous implementation called count_by_dimension() + list_by_dimension()
per dimension (N+1 pattern). The fix introduces list_all() and groups by
dimension in Python.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.data.fs.report_parser._evidence_sqlite import load_evidence_map_from_db


def _insert(repo, practice_id, dimension, verdict="violation", line=1):
    repo.insert_finding({
        "p": practice_id,
        "d": dimension,
        "file": "src/x.py",
        "line": line,
        "t": verdict,
        "severity": "minor",
        "reason": "test reason",
        "snippet": "code here",
        "w": "test",
    })


def test_load_evidence_map_groups_correctly_across_dimensions(tmp_path: Path):
    """Findings in multiple dimensions are grouped correctly by list_all()."""
    repo = SqliteFindingsRepository(tmp_path)
    _insert(repo, "P1", "security", "violation", line=1)
    _insert(repo, "P1", "security", "violation", line=2)
    _insert(repo, "P2", "security", "compliance", line=3)
    _insert(repo, "Q1", "maintainability", "violation", line=4)
    _insert(repo, "Q1", "maintainability", "compliance", line=5)

    result = load_evidence_map_from_db(tmp_path)

    assert set(result.keys()) == {"security", "maintainability"}

    sec = result["security"]
    assert sec["violation_count"] == 2
    assert sec["compliance_count"] == 1
    assert "P1" in sec["principles"]
    assert "P2" in sec["principles"]
    assert len(sec["principles"]["P1"]["violations"]) == 2
    assert len(sec["principles"]["P2"]["compliance"]) == 1

    maint = result["maintainability"]
    assert maint["violation_count"] == 1
    assert maint["compliance_count"] == 1
    assert "Q1" in maint["principles"]


def test_load_evidence_map_uses_list_all_not_loop(tmp_path: Path):
    """load_evidence_map_from_db calls list_all() (not list_by_dimension N+1)."""
    repo = SqliteFindingsRepository(tmp_path)
    _insert(repo, "P1", "security", line=1)
    _insert(repo, "Q1", "reliability", line=2)

    list_all_calls = []
    list_by_dim_calls = []

    original_list_all = SqliteFindingsRepository.list_all

    def _spy_list_all(self):
        list_all_calls.append(1)
        return original_list_all(self)

    def _spy_list_by_dim(self, dim):
        list_by_dim_calls.append(dim)
        return []

    with (
        patch.object(SqliteFindingsRepository, "list_all", _spy_list_all),
        patch.object(SqliteFindingsRepository, "list_by_dimension", _spy_list_by_dim),
    ):
        result = load_evidence_map_from_db(tmp_path)

    assert len(list_all_calls) == 1, (
        "Expected exactly one list_all() call — the N+1 loop should be gone."
    )
    assert list_by_dim_calls == [], (
        f"list_by_dimension should not be called from load_evidence_map_from_db, "
        f"but was called with: {list_by_dim_calls}"
    )


def test_load_evidence_map_empty_db_returns_empty(tmp_path: Path):
    """An empty database returns an empty dict without error."""
    result = load_evidence_map_from_db(tmp_path)
    assert result == {}


def test_dismissed_verdict_excluded_from_counts(tmp_path: Path):
    """#1487 faithfulness: dismissed findings must not inflate compliance_count.

    The old code derived counts via ``len([j for j in judgments if j.verdict == "compliance"])``
    so dismissed findings were never counted.  The batched grouping loop must
    match that behaviour exactly.
    """
    repo = SqliteFindingsRepository(tmp_path)
    _insert(repo, "P1", "security", "violation", line=1)
    _insert(repo, "P1", "security", "compliance", line=2)
    _insert(repo, "P1", "security", "dismissed", line=3)

    result = load_evidence_map_from_db(tmp_path)

    sec = result["security"]
    assert sec["violation_count"] == 1, (
        "violation_count should count only verdict='violation' findings"
    )
    assert sec["compliance_count"] == 1, (
        "compliance_count must NOT include dismissed findings — got "
        f"{sec['compliance_count']}, expected 1"
    )


def test_list_all_method_exists_on_repository(tmp_path: Path):
    """SqliteFindingsRepository exposes list_all()."""
    repo = SqliteFindingsRepository(tmp_path)
    _insert(repo, "P1", "security", line=1)
    findings = repo.list_all()
    assert len(findings) == 1
    assert findings[0].dimension == "security"
    assert findings[0].practice_id == "P1"
