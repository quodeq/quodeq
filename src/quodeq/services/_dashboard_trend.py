"""Accumulated-trend builder for the dashboard module."""
from __future__ import annotations

from typing import Any, Callable

from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services.ports import RunInfo, most_frequent_grade, parse_numeric_score
from quodeq.services.accumulated import numeric_average


def _build_dimension_details(
    run_dims: list[DimensionResult],
    prev_by_dim: dict[str, DimensionResult],
) -> list[dict[str, Any]]:
    """Build per-dimension detail dicts with score deltas for a single run."""
    details = []
    for dim in sorted(run_dims, key=lambda d: d.dimension or ""):
        if not dim.dimension:
            continue
        prev = prev_by_dim.get(dim.dimension)
        score = parse_numeric_score(dim.overall_score) if dim.overall_score else None
        prev_score = parse_numeric_score(prev.overall_score) if prev and prev.overall_score else None
        delta = round(score - prev_score, 2) if score is not None and prev_score is not None else None
        details.append({
            "dimension": dim.dimension,
            "score": score,
            "grade": dim.overall_grade,
            "delta": delta,
        })
    return details


def build_accumulated_trend(
    runs: list[RunInfo],
    get_run_dimensions: Callable[[str], list[DimensionResult]],
    params: ScoringParams | None = None,
) -> list[dict[str, Any]]:
    """Build trend using accumulated scores across all runs (oldest to newest).

    When *params* is None, the saved grade-formula params are loaded so the
    per-run and accumulated grade labels honour the user's custom formula.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    trend: list[dict[str, Any]] = []
    acc_by_dim: dict[str, DimensionResult] = {}
    prev_by_dim: dict[str, DimensionResult] = {}
    for item in reversed(runs):  # oldest -> newest
        run_dims = get_run_dimensions(item.run_id)
        for dim in run_dims:
            if dim.dimension:
                acc_by_dim[dim.dimension] = dim
        if not run_dims:
            continue
        acc_dims = list(acc_by_dim.values())
        acc_grades = [d.overall_grade for d in acc_dims if d.overall_grade]
        acc_avg = numeric_average(acc_dims, params)
        run_avg = numeric_average(run_dims, params)
        run_grades = [d.overall_grade for d in run_dims if d.overall_grade]
        run_dim_names = sorted(d.dimension for d in run_dims if d.dimension)
        dim_details = _build_dimension_details(run_dims, prev_by_dim)
        for dim in run_dims:
            if dim.dimension:
                prev_by_dim[dim.dimension] = dim
        trend.append(
            {
                "runId": item.run_id,
                "dateISO": item.date_iso,
                "dateLabel": item.date_label,
                # Surface the run's lifecycle state so the History row can
                # render "running" instead of a misleading completion time
                # while the evaluation is still in progress (some dims have
                # scored, others haven't).
                "status": item.status,
                "dimensionsCount": len(run_dim_names),
                "dimensions": run_dim_names,
                "dimensionDetails": dim_details,
                "accumulatedDimensionsCount": len(acc_by_dim),
                "runNumericAverage": run_avg,
                "runOverallGrade": (
                    score_to_grade_label(run_avg, params=params) if run_avg is not None
                    else (most_frequent_grade(run_grades) if run_grades else None)
                ),
                "numericAverage": acc_avg,
                "overallGrade": (
                    score_to_grade_label(acc_avg, params=params) if acc_avg is not None
                    else (most_frequent_grade(acc_grades) if acc_grades else None)
                ),
            }
        )
    trend.reverse()
    return trend
