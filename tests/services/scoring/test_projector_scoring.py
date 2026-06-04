"""Unit + parity tests for canonical projector_scoring.

The parity tests compare projector_scoring output to legacy rescore_dimensions
for known inputs. Both call the same scoring internals, so parity is structural --
the tests guard against drift.
"""
from __future__ import annotations

from quodeq.core.types.finding import Finding
from quodeq.services.scoring.projector_scoring import (
    compute_dimension_score,
    compute_principle_grade,
    compute_run_score,
)


def _f(req: str, principle: str, severity: str = "medium", verdict: str = "violation") -> Finding:
    return Finding(
        practice_id=principle, verdict=verdict, file="a.py", line=1,
        end_line=1, title="t", reason="r", snippet="s", severity=severity,
        cwe=None, req=req, req_refs=[], context="", dimension="Security",
        violation_type=None, scope="", confidence=100,
    )


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


def test_compute_dimension_score_averages_principle_scores() -> None:
    p1 = {"principle_id": "P1", "score": 6.0, "grade": "C", "finding_count": 1, "dismissed_count": 0}
    p2 = {"principle_id": "P2", "score": 8.0, "grade": "B", "finding_count": 1, "dismissed_count": 0}

    result = compute_dimension_score(dimension="Security", principle_grades=[p1, p2])

    assert result["dimension"] == "Security"
    assert result["score"] == 7.0


def test_compute_dimension_score_skips_insufficient_principles() -> None:
    p1 = {"principle_id": "P1", "score": None, "grade": "Insufficient", "finding_count": 0, "dismissed_count": 0}
    p2 = {"principle_id": "P2", "score": 8.0, "grade": "B", "finding_count": 1, "dismissed_count": 0}

    result = compute_dimension_score(dimension="Security", principle_grades=[p1, p2])

    assert result["score"] == 8.0


def test_compute_dimension_score_all_insufficient_returns_none() -> None:
    p1 = {"principle_id": "P1", "score": None, "grade": "Insufficient", "finding_count": 0, "dismissed_count": 0}

    result = compute_dimension_score(dimension="Security", principle_grades=[p1])

    assert result["score"] is None
    assert result["grade"] == "Insufficient"


def test_compute_run_score_averages_dimension_scores() -> None:
    d1 = {"dimension": "Security", "score": 7.0, "grade": "B-"}
    d2 = {"dimension": "Reliability", "score": 9.0, "grade": "A"}

    result = compute_run_score([d1, d2])

    assert result["score"] == 8.0


def test_compute_run_score_empty_returns_none() -> None:
    result = compute_run_score([])
    assert result == {"score": None, "grade": None}


def test_compute_run_score_skips_null_scores() -> None:
    d1 = {"dimension": "Security", "score": 8.0, "grade": "A-"}
    d2 = {"dimension": "Reliability", "score": None, "grade": "Insufficient"}

    result = compute_run_score([d1, d2])

    assert result["score"] == 8.0  # only Security counts


# --- Parity tests: projector_scoring vs legacy rescore_dimensions ----------
#
# Both engines now apply the same confidence-level check (see
# ``core.evidence.model.classify_confidence_level``) so they agree on which
# principles qualify for scoring vs Insufficient.  Inputs below carry enough
# findings to clear the medium-confidence threshold (5 by default at
# source_file_count=0), so both engines score the principles instead of
# bailing out to Insufficient.


def _legacy_dim_score(violations, compliance) -> float | None:
    """Compute a dimension score via the underlying legacy scoring path.

    Calls _score_principle per principle and weighted_overall to aggregate,
    mirroring exactly what _rescore_dimension does after filtering dismissed
    findings.
    """
    from quodeq.services.rescore import _score_all_principles, _group_by_principle
    from quodeq.core.scoring.overall import weighted_overall, MODE_NUMERICAL

    pv = _group_by_principle(violations)
    pc = _group_by_principle(compliance)
    principle_scores, _ = _score_all_principles(pv, pc)
    overall = weighted_overall(principle_scores, MODE_NUMERICAL)
    return overall.weighted_score


def _new_dim_score(violations, compliance) -> float | None:
    """Compute the same dimension score via projector_scoring."""
    violations_by: dict = {}
    for v in violations:
        violations_by.setdefault(v.practice_id, []).append(v)
    comp_by: dict = {}
    for c in compliance:
        comp_by.setdefault(c.practice_id, []).append(c)
    p_grades = [
        compute_principle_grade(
            principle_id=p,
            findings=violations_by.get(p, []),
            compliance=comp_by.get(p, []),
        )
        for p in sorted(set(violations_by) | set(comp_by))
    ]
    return compute_dimension_score(dimension="Security", principle_grades=p_grades)["score"]


def test_parity_single_principle_sufficient_violations() -> None:
    """5 same-severity violations clears the medium-confidence floor."""
    violations = [_f(f"R{i}", "P1", "high") for i in range(5)]
    compliance = []
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_single_principle_violation_and_compliance() -> None:
    violations = [_f(f"V{i}", "P1", "high") for i in range(3)]
    compliance = [_f(f"C{i}", "P1", "low", verdict="compliance") for i in range(2)]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_multiple_principles() -> None:
    """Each principle has enough findings to clear the confidence floor."""
    violations = [_f(f"V{i}", "P1", "high") for i in range(3)] \
        + [_f(f"W{i}", "P2", "critical") for i in range(3)]
    compliance = [_f(f"C{i}", "P1", "low", verdict="compliance") for i in range(2)] \
        + [_f(f"D{i}", "P2", "low", verdict="compliance") for i in range(2)]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_low_confidence_returns_insufficient_in_both() -> None:
    """Thin evidence (1 finding) must yield Insufficient in both engines.

    This is the contract that closed the dashboard-vs-CLI score split.
    Score may be ``None`` (projector) or ``0.0`` (legacy weighted_overall
    fallback), but the *grade* must be Insufficient.
    """
    from quodeq.services.rescore import _score_all_principles, _group_by_principle
    from quodeq.core.scoring.overall import weighted_overall, MODE_NUMERICAL

    violations = [_f("R1", "P1", "high")]
    compliance = []

    # Legacy
    pv = _group_by_principle(violations)
    pc = _group_by_principle(compliance)
    legacy_principle_scores, _ = _score_all_principles(pv, pc)
    legacy_overall = weighted_overall(legacy_principle_scores, MODE_NUMERICAL)
    assert legacy_overall.grade == "Insufficient"

    # New
    p_grade = compute_principle_grade(principle_id="P1", findings=violations, compliance=[])
    assert p_grade["grade"] == "Insufficient"
    new_dim = compute_dimension_score(dimension="Security", principle_grades=[p_grade])
    assert new_dim["grade"] == "Insufficient"
