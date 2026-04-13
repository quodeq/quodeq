"""Build accumulated state across runs with dismissals applied server-side."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.services.ports import RunInfo, calculate_trend, most_frequent_grade
from quodeq.services.scoring._run_scores import get_run_dimensions, parse_score
from quodeq.services.scoring._rescore import rescore_run
from quodeq.services.scoring._types import (
    AccumulatedSummary,
    ScoredDimension,
)


def build_accumulated(
    reports_root: Path,
    project: str,
    all_runs: list[RunInfo],
) -> tuple[list[ScoredDimension], AccumulatedSummary]:
    """Build accumulated dimensions and summary across all runs.

    Walks runs newest-first, keeping the latest occurrence of each
    dimension. Applies dismissals via rescore_run for each run that
    contributes a dimension.

    Returns (dimensions, summary).
    """
    # Track which runs we need to rescore (only those contributing a latest dimension)
    latest_by_dim: dict[str, tuple[ScoredDimension, RunInfo]] = {}
    prev_occurrence: dict[str, ScoredDimension] = {}
    prev_run_latest: dict[str, ScoredDimension] = {}

    # Cache rescored runs to avoid re-rescoring the same run
    rescored_cache: dict[str, dict[str, ScoredDimension]] = {}

    for run_idx, run_info in enumerate(all_runs):
        run_id = run_info.run_id
        if run_id not in rescored_cache:
            scored_dims = rescore_run(reports_root, project, run_id)
            rescored_cache[run_id] = {sd.dimension.lower(): sd for sd in scored_dims}

        run_dims = rescored_cache[run_id]
        for dim_key, sd in run_dims.items():
            if not sd.dimension:
                continue
            # Enrich with run metadata
            enriched = ScoredDimension(
                dimension=sd.dimension,
                overall_score=sd.overall_score,
                overall_grade=sd.overall_grade,
                violation_count=sd.violation_count,
                compliance_count=sd.compliance_count,
                severity_critical=sd.severity_critical,
                severity_major=sd.severity_major,
                severity_minor=sd.severity_minor,
                from_run_id=run_id,
                from_date_iso=run_info.date_iso,
                from_date_label=run_info.date_label,
            )
            if dim_key not in latest_by_dim:
                latest_by_dim[dim_key] = (enriched, run_info)
            elif dim_key not in prev_occurrence:
                prev_occurrence[dim_key] = enriched
            # First non-latest run's dimensions for previous average
            if run_idx > 0 and dim_key not in prev_run_latest:
                prev_run_latest[dim_key] = enriched

    # Compute trends by comparing latest to previous occurrence
    dimensions: list[ScoredDimension] = []
    for dim_key, (sd, _run_info) in latest_by_dim.items():
        prev = prev_occurrence.get(dim_key)
        trend_str = _compute_trend(sd.overall_score, prev.overall_score if prev else None)
        dimensions.append(ScoredDimension(
            dimension=sd.dimension,
            overall_score=sd.overall_score,
            overall_grade=sd.overall_grade,
            violation_count=sd.violation_count,
            compliance_count=sd.compliance_count,
            severity_critical=sd.severity_critical,
            severity_major=sd.severity_major,
            severity_minor=sd.severity_minor,
            trend=trend_str,
            previous_score=prev.overall_score if prev else None,
            previous_run_id=prev.from_run_id if prev else None,
            from_run_id=sd.from_run_id,
            from_date_iso=sd.from_date_iso,
            from_date_label=sd.from_date_label,
            from_project=sd.from_project,
            stale=sd.stale,
        ))

    # Build summary
    summary = _build_summary(dimensions, list(prev_run_latest.values()))
    return dimensions, summary


def build_accumulated_with_children(
    reports_root: Path,
    project: str,
    own_runs: list[RunInfo],
    children: list[str],
) -> tuple[list[ScoredDimension], AccumulatedSummary]:
    """Build accumulated state including child project dimensions."""
    from quodeq.services.ports import list_runs

    all_dims: list[ScoredDimension] = []
    if own_runs:
        own_dims, _ = build_accumulated(reports_root, project, own_runs)
        all_dims.extend(own_dims)

    for child in children:
        child_runs = list_runs(reports_root, child)
        if not child_runs:
            continue
        child_dims, _ = build_accumulated(reports_root, child, child_runs)
        # Tag each dimension with its source child project
        for sd in child_dims:
            all_dims.append(ScoredDimension(
                dimension=sd.dimension,
                overall_score=sd.overall_score,
                overall_grade=sd.overall_grade,
                violation_count=sd.violation_count,
                compliance_count=sd.compliance_count,
                severity_critical=sd.severity_critical,
                severity_major=sd.severity_major,
                severity_minor=sd.severity_minor,
                trend=sd.trend,
                previous_score=sd.previous_score,
                previous_run_id=sd.previous_run_id,
                from_run_id=sd.from_run_id,
                from_date_iso=sd.from_date_iso,
                from_date_label=sd.from_date_label,
                from_project=child,
                stale=sd.stale,
            ))

    summary = _build_summary(all_dims, [])
    return all_dims, summary


def _compute_trend(current: float | None, previous: float | None) -> str:
    """Compute trend string from numeric scores."""
    if current is None or previous is None:
        return "none"
    diff = current - previous
    if abs(diff) < 0.05:
        return "same"
    return "up" if diff > 0 else "down"


def _build_summary(
    dimensions: list[ScoredDimension],
    prev_dims: list[ScoredDimension],
) -> AccumulatedSummary:
    """Build an AccumulatedSummary from dimensions."""
    scores = [d.overall_score for d in dimensions if d.overall_score is not None]
    avg = round(sum(scores) / len(scores), 1) if scores else None
    prev_scores = [d.overall_score for d in prev_dims if d.overall_score is not None]
    prev_avg = round(sum(prev_scores) / len(prev_scores), 1) if prev_scores else None

    grades = [d.overall_grade for d in dimensions if d.overall_grade]
    overall_grade = (
        score_to_grade_label(avg) if avg is not None
        else most_frequent_grade(grades) if grades else None
    )

    total_v = sum(d.violation_count for d in dimensions)
    total_c = sum(d.compliance_count for d in dimensions)
    crit = sum(d.severity_critical for d in dimensions)
    maj = sum(d.severity_major for d in dimensions)
    minor = sum(d.severity_minor for d in dimensions)

    return AccumulatedSummary(
        overall_grade=overall_grade,
        numeric_average=avg,
        previous_numeric_average=prev_avg,
        total_violations=total_v,
        total_compliance=total_c,
        dimension_count=len(dimensions),
        severity_critical=crit,
        severity_major=maj,
        severity_minor=minor,
    )
