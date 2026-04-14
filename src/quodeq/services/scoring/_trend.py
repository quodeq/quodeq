"""Build trend from runs with accumulated progression and dismissals applied."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.services.ports import RunInfo, most_frequent_grade
from quodeq.services.scoring._rescore import rescore_run
from quodeq.services.scoring._types import ScoredDimension, TrendEntry


def _compute_average(dims: list[ScoredDimension]) -> float | None:
    """Compute the rounded average score from a list of scored dimensions."""
    scores = [d.overall_score for d in dims if d.overall_score is not None]
    return round(sum(scores) / len(scores), 1) if scores else None


def _grade_from_average(avg: float | None, grades: list[str]) -> str | None:
    """Derive overall grade from numeric average or most frequent grade."""
    if avg is not None:
        return score_to_grade_label(avg)
    return most_frequent_grade(grades) if grades else None


def _build_trend_entry(
    run_info: RunInfo, run_dims: list[ScoredDimension],
    acc_by_dim: dict[str, ScoredDimension],
    prev_by_dim: dict[str, ScoredDimension],
) -> TrendEntry:
    """Build a single TrendEntry from a run's dimensions and accumulated state."""
    details = _build_dimension_details(run_dims, prev_by_dim)
    acc_dims = list(acc_by_dim.values())
    acc_avg = _compute_average(acc_dims)
    run_avg = _compute_average(run_dims)
    run_dim_names = sorted(d.dimension for d in run_dims if d.dimension)

    return TrendEntry(
        run_id=run_info.run_id,
        date_iso=run_info.date_iso,
        date_label=run_info.date_label,
        dimensions_count=len(run_dim_names),
        dimensions=run_dim_names,
        dimension_details=details,
        accumulated_dimensions_count=len(acc_by_dim),
        run_numeric_average=run_avg,
        run_overall_grade=_grade_from_average(
            run_avg, [d.overall_grade for d in run_dims if d.overall_grade],
        ),
        numeric_average=acc_avg,
        overall_grade=_grade_from_average(
            acc_avg, [d.overall_grade for d in acc_dims if d.overall_grade],
        ),
    )


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

        for sd in run_dims:
            if sd.dimension:
                acc_by_dim[sd.dimension.lower()] = sd

        trend.append(_build_trend_entry(run_info, run_dims, acc_by_dim, prev_by_dim))

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
