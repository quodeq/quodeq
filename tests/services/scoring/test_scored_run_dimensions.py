"""Unit tests for the shared ``scored_run_dimensions`` helper.

``scored_run_dimensions`` is the single seam every per-run read path routes
through so the SAME run+dimension reports the SAME (dismiss-adjusted) score
regardless of which endpoint asked. It = ``read_run_data`` + project-wide
``rescore`` and returns ``DimensionResult`` objects (not camelCase dicts).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult

import quodeq.services.scoring as scoring


def _make_violation(practice_id="P1", severity="major", req="R1", file="a.py", line=1):
    return Finding(
        practice_id=practice_id, severity=severity, req=req, file=file, line=line, reason="bug",
    )


def _make_compliance(practice_id="P1", req="C1", file="c.py", line=20):
    return Finding(practice_id=practice_id, req=req, file=file, line=line, reason="ok")


def _make_dimension(violations, compliance):
    return DimensionResult(
        dimension="performance",
        overall_score="6.1/10",
        overall_grade="Adequate",
        principles=[PrincipleGrade(principle="P1", score="6.1/10", grade="Adequate")],
        violations=violations,
        compliance=compliance,
        totals=Totals(
            violation_count=len(violations),
            compliance_count=len(compliance),
            severity=SeverityTally(
                critical=sum(1 for v in violations if v.severity == "critical"),
                major=sum(1 for v in violations if v.severity == "major"),
                minor=sum(1 for v in violations if v.severity == "minor"),
            ),
        ),
        source_file_count=100,
    )


def test_scored_run_dimensions_applies_project_wide_dismissal(monkeypatch):
    """A dismissed violation must move the returned dimension score.

    Mirrors the real-data disparity: raw read_run_data reports one score,
    the project-wide rescore reports a higher one after a false positive is
    dismissed. The helper must return the rescored DimensionResult objects.
    """
    crit = _make_violation(severity="critical", req="R1", file="a.py", line=1)
    extras = [
        _make_violation(severity="major", req=f"R{i}", file=f"f{i}.py", line=10)
        for i in range(2, 6)
    ]
    compliance = [_make_compliance(req=f"C{i}", file=f"c{i}.py", line=20) for i in range(5)]
    raw_dim = _make_dimension([crit, *extras], compliance)

    monkeypatch.setattr(scoring, "read_run_data", lambda root, p, r: [raw_dim])
    monkeypatch.setattr(scoring, "dismissed_keys", lambda pdir: {("R1", "a.py", 1)})
    monkeypatch.setattr(scoring, "deleted_keys", lambda pdir: set())

    result = scoring.scored_run_dimensions(Path("/reports"), "proj", "run1")

    assert len(result) == 1
    dim = result[0]
    # Return type must be DimensionResult objects, not camelCase dicts.
    assert isinstance(dim, DimensionResult)
    # The dismissed critical is gone from the violations list.
    reqs = {v.req for v in dim.violations}
    assert "R1" not in reqs
    # And the score moved up relative to the raw score.
    raw_num = float(raw_dim.overall_score.split("/")[0])
    new_num = float(dim.overall_score.split("/")[0])
    assert new_num > raw_num, f"dismissing the critical should raise the score; {raw_num} -> {new_num}"


def test_scored_run_dimensions_no_dismissals_returns_unchanged(monkeypatch):
    """With no dismissals/deletions, the raw dimensions pass through untouched."""
    raw_dim = _make_dimension([_make_violation()], [_make_compliance()])
    monkeypatch.setattr(scoring, "read_run_data", lambda root, p, r: [raw_dim])
    monkeypatch.setattr(scoring, "dismissed_keys", lambda pdir: set())
    monkeypatch.setattr(scoring, "deleted_keys", lambda pdir: set())

    result = scoring.scored_run_dimensions(Path("/reports"), "proj", "run1")

    assert [d.overall_score for d in result] == [raw_dim.overall_score]


def test_scored_run_dimensions_validates_path_segments(monkeypatch):
    """Path-traversal segments are rejected like read_run_data does."""
    monkeypatch.setattr(scoring, "read_run_data", lambda root, p, r: [])
    monkeypatch.setattr(scoring, "dismissed_keys", lambda pdir: set())
    monkeypatch.setattr(scoring, "deleted_keys", lambda pdir: set())
    with pytest.raises(ValueError):
        scoring.scored_run_dimensions(Path("/reports"), "../etc", "run1")
