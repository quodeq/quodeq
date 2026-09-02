"""Unit tests for canonical projector_scoring — compute_principle_grade.

Split from test_projector_scoring.py. Shared `_f` finding builder lives in
tests/core/_projector_scoring_fixtures.py.
"""
from __future__ import annotations

from quodeq.core.scoring.projector_scoring import compute_principle_grade

from tests.core._projector_scoring_fixtures import _f


def test_compute_principle_grade_single_violation_is_insufficient() -> None:
    """One finding total is below the medium-confidence threshold; the
    projector must short-circuit to Insufficient to match the CLI engine's
    ``core.scoring._principle._score_numerical`` behaviour. Previously this
    came out as a real score, which is what made the SQL grade tables
    disagree with the CLI's evaluation JSON."""
    finding = _f("R1", "P1", severity="high", verdict="violation")

    result = compute_principle_grade(
        principle_id="P1", findings=[finding], compliance=[],
    )

    assert result["principle_id"] == "P1"
    assert result["grade"] == "Insufficient"
    assert result["score"] is None
    assert result["finding_count"] == 1
    assert result["dismissed_count"] == 0


def test_compute_principle_grade_sufficient_evidence_scores_normally() -> None:
    """With enough findings to clear the confidence floor, scoring runs."""
    findings = [_f(f"R{i}", "P1", severity="medium") for i in range(5)]

    result = compute_principle_grade(
        principle_id="P1", findings=findings, compliance=[],
    )

    assert result["grade"] != "Insufficient"
    assert result["score"] is not None
    assert result["finding_count"] == 5


def test_compute_principle_grade_only_dismissed_returns_insufficient() -> None:
    """Caller filters by verdict != 'dismissed' before passing; this models the case
    where the only findings for a principle were dismissed."""
    result = compute_principle_grade(
        principle_id="P1", findings=[], compliance=[], dismissed_count=2,
    )

    assert result["grade"] == "Insufficient"
    assert result["score"] is None
    assert result["dismissed_count"] == 2
