"""Build trend from runs with accumulated progression and dismissals applied."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.services.ports import RunInfo, most_frequent_grade
from quodeq.services.scoring._rescore import rescore_run
from quodeq.services.scoring._types import ScoredDimension, TrendEntry


def build_trend(
    reports_root: Path,
    project: str,
    runs: list[RunInfo],
) -> list[TrendEntry]:
    """Build trend with accumulated progression, dismissals applied server-side.

    Walks runs oldest-first to build accumulated state at each point.
    Returns trend entries newest-first (matching frontend convention).
    """
    trend: list[TrendEntry] = []
    acc_by_dim: dict[str, ScoredDimension] = {}
    prev_by_dim: dict[str, ScoredDimension] = {}

    for run_info in reversed(runs):  # oldest -> newest
        run_dims = rescore_run(reports_root, project, run_info.run_id)
        if not run_dims:
            continue

        # Update accumulated state
        for sd in run_dims:
            if sd.dimension:
                acc_by_dim[sd.dimension.lower()] = sd

        # Build dimension details with deltas
        details = _build_dimension_details(run_dims, prev_by_dim)

        # Compute averages
        acc_dims = list(acc_by_dim.values())
        acc_scores = [d.overall_score for d in acc_dims if d.overall_score is not None]
        acc_avg = round(sum(acc_scores) / len(acc_scores), 1) if acc_scores else None
        run_scores = [d.overall_score for d in run_dims if d.overall_score is not None]
        run_avg = round(sum(run_scores) / len(run_scores), 1) if run_scores else None

        acc_grades = [d.overall_grade for d in acc_dims if d.overall_grade]
        run_grades = [d.overall_grade for d in run_dims if d.overall_grade]
        run_dim_names = sorted(d.dimension for d in run_dims if d.dimension)

        trend.append(TrendEntry(
            run_id=run_info.run_id,
            date_iso=run_info.date_iso,
            date_label=run_info.date_label,
            dimensions_count=len(run_dim_names),
            dimensions=run_dim_names,
            dimension_details=details,
            accumulated_dimensions_count=len(acc_by_dim),
            run_numeric_average=run_avg,
            run_overall_grade=(
                score_to_grade_label(run_avg) if run_avg is not None
                else (most_frequent_grade(run_grades) if run_grades else None)
            ),
            numeric_average=acc_avg,
            overall_grade=(
                score_to_grade_label(acc_avg) if acc_avg is not None
                else (most_frequent_grade(acc_grades) if acc_grades else None)
            ),
        ))

        # Track previous for next iteration
        for sd in run_dims:
            if sd.dimension:
                prev_by_dim[sd.dimension.lower()] = sd

    trend.reverse()  # newest first
    return trend


def _build_dimension_details(
    run_dims: list[ScoredDimension],
    prev_by_dim: dict[str, ScoredDimension],
) -> list[dict]:
    """Build per-dimension detail dicts with score deltas."""
    details = []
    for sd in sorted(run_dims, key=lambda d: d.dimension or ""):
        if not sd.dimension:
            continue
        prev = prev_by_dim.get(sd.dimension.lower())
        score = sd.overall_score
        prev_score = prev.overall_score if prev else None
        delta = (
            round(score - prev_score, 2)
            if score is not None and prev_score is not None
            else None
        )
        details.append({
            "dimension": sd.dimension,
            "score": score,
            "grade": sd.overall_grade,
            "delta": delta,
        })
    return details
