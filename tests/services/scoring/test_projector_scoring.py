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


# --- params threading ---------------------------------------------------------
import dataclasses

from quodeq.core.scoring.params import DEFAULT_PARAMS


def test_compute_dimension_score_with_custom_thresholds_changes_grade():
    params = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=(
        (9.9, "Exemplary"), (9.0, "Good"), (8.0, "Adequate"), (7.0, "Poor"),
    ))
    from quodeq.services.scoring.projector_scoring import compute_dimension_score
    grades = [{"score": 8.5, "grade": "Good"}]
    result = compute_dimension_score(
        dimension="security", principle_grades=grades, params=params,
    )
    assert result["grade"] == "Adequate"


def test_compute_run_score_applies_dimension_weights_when_enabled():
    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=True)
    from quodeq.services.scoring.projector_scoring import compute_run_score
    dims = [
        {"dimension": "security", "score": 8.0},
        {"dimension": "performance", "score": 6.0},
    ]
    result = compute_run_score(dims, params=params)
    # security 1.2, performance 0.8 → (8*1.2 + 6*0.8) / 2.0 = 7.2
    assert result["score"] == 7.2


def test_compute_run_score_plain_mean_when_disabled():
    from quodeq.services.scoring.projector_scoring import compute_run_score
    dims = [
        {"dimension": "security", "score": 8.0},
        {"dimension": "performance", "score": 6.0},
    ]
    assert compute_run_score(dims)["score"] == 7.0


def test_summary_builders_agree_under_dimension_weights():
    """SQL-path and eval-files-path summaries must produce the same weighted average."""
    from quodeq.core.types.dimension import DimensionResult
    from quodeq.data.fs.report_parser._summary import summarize_dimensions
    from quodeq.services.scoring import _build_summary_from_dim_dicts

    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=True)

    dims = [
        DimensionResult(dimension="security", overall_grade="Good", overall_score="8.0/10"),
        DimensionResult(dimension="performance", overall_grade="Adequate", overall_score="6.0/10"),
    ]
    legacy = summarize_dimensions(dims, params=params)

    dim_dicts = [
        {"dimension": "security", "overallScore": "8.0/10", "overallGrade": "Good"},
        {"dimension": "performance", "overallScore": "6.0/10", "overallGrade": "Adequate"},
    ]
    sql = _build_summary_from_dim_dicts(dim_dicts, params=params)

    # security 1.2, performance 0.8 → (8.0*1.2 + 6.0*0.8) / (1.2 + 0.8) = 7.2 weighted (vs 7.0 plain)
    assert legacy.numeric_average == 7.2
    assert sql["numericAverage"] == 7.2
    assert sql["overallGrade"] == legacy.overall_grade


# --- read-time aggregation honours saved params (dashboard summary, trend) ----
#
# Regression guards for the three read-time aggregation points that used to
# fall back to DEFAULT_PARAMS while the rest of the stack threaded the saved
# grade-formula params: recompute_summary (accumulated summary rescore) and
# build_accumulated_trend (history chart labels).

_CUSTOM_THRESHOLDS = (
    (9.9, "Exemplary"), (9.8, "Good"), (9.7, "Adequate"), (0.1, "Poor"),
)


def test_recompute_summary_uses_custom_thresholds_for_overall_grade():
    """A ~7.0 average lands in the custom 'Poor' band, not the default
    'Good'/'Adequate'. Without threading params, recompute_summary labelled
    it under DEFAULT_PARAMS thresholds (the accumulated-grade mislabel bug)."""
    from quodeq.services.scoring._summary import recompute_summary

    params = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=_CUSTOM_THRESHOLDS)
    dims = [
        {"dimension": "security", "overallScore": "8.0/10", "overallGrade": "Good"},
        {"dimension": "performance", "overallScore": "6.0/10", "overallGrade": "Adequate"},
    ]

    # Sanity: under the default formula this avg (7.0) is NOT "Poor".
    default_summary = recompute_summary(dims, {})
    assert default_summary["overallGrade"] != "Poor"

    summary = recompute_summary(dims, {}, params=params)
    assert summary["numericAverage"] == 7.0
    assert summary["overallGrade"] == "Poor"


def test_recompute_summary_applies_dimension_weights_when_enabled():
    """With dimension weights on, the average is weighted (security 1.2,
    performance 0.8) → 7.2, not the plain mean 7.0."""
    from quodeq.services.scoring._summary import recompute_summary

    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=True)
    dims = [
        {"dimension": "security", "overallScore": "8.0/10", "overallGrade": "Good"},
        {"dimension": "performance", "overallScore": "6.0/10", "overallGrade": "Adequate"},
    ]

    summary = recompute_summary(dims, {}, params=params)
    # (8.0*1.2 + 6.0*0.8) / (1.2 + 0.8) = 7.2
    assert summary["numericAverage"] == 7.2


def test_build_accumulated_trend_uses_custom_thresholds_for_run_grade():
    """The trend builder's run/accumulated grade labels must reflect the
    custom thresholds. Build the full public input (a RunInfo list + a
    dict-backed fetcher) since constructing those is cheap, rather than
    testing an internal helper."""
    from quodeq.core.types.dimension import DimensionResult
    from quodeq.data.fs.report_parser._run_info import RunInfo
    from quodeq.services._dashboard_trend import build_accumulated_trend

    params = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=_CUSTOM_THRESHOLDS)

    run = RunInfo(run_id="r1", date_iso="2026-06-10", date_label="Jun 10")
    dims = [
        DimensionResult(dimension="security", overall_grade="Good", overall_score="8.0/10"),
        DimensionResult(dimension="performance", overall_grade="Adequate", overall_score="6.0/10"),
    ]

    def fetcher(run_id: str) -> list[DimensionResult]:
        return dims if run_id == "r1" else []

    # Default formula: ~7.0 avg is not "Poor".
    default_trend = build_accumulated_trend([run], fetcher)
    assert default_trend[0]["runOverallGrade"] != "Poor"

    trend = build_accumulated_trend([run], fetcher, params=params)
    assert trend[0]["runNumericAverage"] == 7.0
    assert trend[0]["runOverallGrade"] == "Poor"
    assert trend[0]["overallGrade"] == "Poor"
