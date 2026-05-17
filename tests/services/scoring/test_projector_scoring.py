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


def test_compute_principle_grade_single_violation() -> None:
    finding = _f("R1", "P1", severity="high", verdict="violation")

    result = compute_principle_grade(
        principle_id="P1", findings=[finding], compliance=[],
    )

    assert result["principle_id"] == "P1"
    assert result["score"] is not None
    assert result["grade"] is not None
    assert result["finding_count"] == 1
    assert result["dismissed_count"] == 0


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

def _legacy_dim_score(violations, compliance) -> float | None:
    """Compute a dimension score via the underlying legacy scoring path.

    Calls _score_principle per principle and weighted_overall to aggregate,
    mirroring exactly what _rescore_dimension does after filtering dismissed
    findings. Does NOT call rescore_dimensions, which short-circuits when no
    findings are dismissed and would return a stale pre-computed score string.
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


def test_parity_single_principle_single_violation() -> None:
    violations = [_f("R1", "P1", "high")]
    compliance = []
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_single_principle_violation_and_compliance() -> None:
    violations = [_f("R1", "P1", "high"), _f("R2", "P1", "medium")]
    compliance = [_f("R3", "P1", "low", verdict="compliance")]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_multiple_principles() -> None:
    violations = [
        _f("R1", "P1", "high"), _f("R2", "P1", "medium"),
        _f("R3", "P2", "critical"),
    ]
    compliance = [_f("R4", "P1", "low", verdict="compliance")]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_mixed_with_insufficient_principle() -> None:
    """Critical landmine: legacy aggregates principles into dimensions then averages dimensions,
    while compute_run_score in the new path averages dimension scores directly. For a single
    dimension this should be equivalent -- verify here. (The run-level parity is tested elsewhere.)"""
    violations = [_f("R1", "P1", "high")]
    compliance = [_f("R2", "P2", "low", verdict="compliance")]  # P2 has only compliance -> may be Insufficient
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"
