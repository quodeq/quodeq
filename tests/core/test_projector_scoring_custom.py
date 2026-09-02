"""Tests for canonical projector_scoring — custom grade-formula params
threading, including read-time aggregation (dashboard summary, trend).

Split from test_projector_scoring.py.

Regression guards for the three read-time aggregation points that used to
fall back to DEFAULT_PARAMS while the rest of the stack threaded the saved
grade-formula params: recompute_summary (accumulated summary rescore) and
build_accumulated_trend (history chart labels).
"""
from __future__ import annotations

import dataclasses

from quodeq.core.scoring.params import DEFAULT_PARAMS

_CUSTOM_THRESHOLDS = (
    (9.9, "Exemplary"), (9.8, "Good"), (9.7, "Adequate"), (0.1, "Poor"),
)


def test_compute_dimension_score_with_custom_thresholds_changes_grade():
    params = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=(
        (9.9, "Exemplary"), (9.0, "Good"), (8.0, "Adequate"), (7.0, "Poor"),
    ))
    from quodeq.core.scoring.projector_scoring import compute_dimension_score
    grades = [{"score": 8.5, "grade": "Good"}]
    result = compute_dimension_score(
        dimension="security", principle_grades=grades, params=params,
    )
    assert result["grade"] == "Adequate"


def test_compute_run_score_applies_dimension_weights_when_enabled():
    params = dataclasses.replace(
        DEFAULT_PARAMS,
        dimension_weights_enabled=True,
        dimension_weights={"security": 1.2, "performance": 0.8},
    )
    from quodeq.core.scoring.projector_scoring import compute_run_score
    dims = [
        {"dimension": "security", "score": 8.0},
        {"dimension": "performance", "score": 6.0},
    ]
    result = compute_run_score(dims, params=params)
    # security 1.2, performance 0.8 → (8*1.2 + 6*0.8) / 2.0 = 7.2
    assert result["score"] == 7.2


def test_compute_run_score_plain_mean_when_disabled():
    from quodeq.core.scoring.projector_scoring import compute_run_score
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

    params = dataclasses.replace(
        DEFAULT_PARAMS,
        dimension_weights_enabled=True,
        dimension_weights={"security": 1.2, "performance": 0.8},
    )

    dims = [
        DimensionResult(dimension="security", overall_grade="Good", overall_score="8.0/10"),
        DimensionResult(dimension="performance", overall_grade="Adequate", overall_score="6.0/10"),
    ]
    legacy = summarize_dimensions(dims, params=params)

    dim_dicts = [
        {"dimension": "security", "overallScore": "8.0/10", "overallGrade": "Good"},
        {"dimension": "performance", "overallScore": "6.0/10", "overallGrade": "Adequate"},
    ]
    # score_pairs are the raw floats a real caller (_build_response_from_grade_tables)
    # builds from the SQL dim_rows -- the same values that were formatted into
    # dim_dicts' "overallScore" display strings above.
    score_pairs = [("security", 8.0), ("performance", 6.0)]
    sql = _build_summary_from_dim_dicts(dim_dicts, params=params, score_pairs=score_pairs)

    # security 1.2, performance 0.8 → (8.0*1.2 + 6.0*0.8) / (1.2 + 0.8) = 7.2 weighted (vs 7.0 plain)
    assert legacy.numeric_average == 7.2
    assert sql["numericAverage"] == 7.2
    assert sql["overallGrade"] == legacy.overall_grade


def test_summary_builder_uses_raw_float_score_pairs_not_display_string():
    """score_pairs are required raw floats, independent of the "overallScore"
    display string -- proving the summary no longer round-trips scores through
    a parsed "X/10" string. The exact float the caller holds must reach
    ``dimension_weighted_average`` unchanged (frozen scoring numbers).
    """
    from quodeq.services.scoring import _build_summary_from_dim_dicts

    # overallScore is deliberately a coarser display string than the raw
    # score; if the summary still parsed it back out, numericAverage would
    # come out as round(8.0, 1) == 8.0 instead of round(tricky_score, 1).
    dim_dicts = [{"dimension": "security", "overallScore": "8/10", "overallGrade": "Good"}]
    tricky_score = 7.666666666666667
    score_pairs = [("security", tricky_score)]

    result = _build_summary_from_dim_dicts(
        dim_dicts, params=DEFAULT_PARAMS, score_pairs=score_pairs,
    )

    # dimension_weighted_average rounds its result to 1 decimal; the input
    # float must flow through identically (same value, no reformat/reparse).
    assert result["numericAverage"] == round(tricky_score, 1)
    assert result["numericAverage"] == 7.7


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

    params = dataclasses.replace(
        DEFAULT_PARAMS,
        dimension_weights_enabled=True,
        dimension_weights={"security": 1.2, "performance": 0.8},
    )
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
