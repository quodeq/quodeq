"""Computation helpers for the accumulated (cross-run) view."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from quodeq.services.ports import calculate_trend, most_frequent_grade, parse_numeric_score
from quodeq.core.types import DimensionResult, to_camel_dict
from quodeq.core.scoring.internals import score_to_grade_label


def _compute_accumulated_trends(
    all_dimensions: list[DimensionResult],
    prev_occurrence: dict[str, DimensionResult],
) -> list[DimensionResult]:
    """Compute trend data for each accumulated dimension using pre-built prev_occurrence."""
    result: list[DimensionResult] = []
    for dim in all_dimensions:
        dim_name = dim.dimension
        previous = prev_occurrence.get(dim_name) if dim_name else None
        trend = calculate_trend(
            dim.overall_score,
            previous.overall_score if previous else None,
        )
        result.append(
            replace(
                dim,
                trend=trend,
                previous_run_id=previous.run_id if previous else None,
                previous_score=previous.overall_score if previous else None,
            )
        )
    return result


def _aggregate_severity_counts(all_dimensions: list[DimensionResult]) -> dict[str, int]:
    """Sum violation/compliance counts and severity buckets across dimensions."""
    total_violations = total_compliance = critical = major = minor = 0
    for dim in all_dimensions:
        totals = dim.totals
        if totals:
            total_violations += totals.violation_count
            total_compliance += totals.compliance_count
            critical += totals.severity.critical
            major += totals.severity.major
            minor += totals.severity.minor
    return {
        "totalViolations": total_violations, "totalCompliance": total_compliance,
        "critical": critical, "major": major, "minor": minor,
    }


def numeric_average(dimensions: list[DimensionResult]) -> float | None:
    """Compute the average numeric score from a list of DimensionResult objects."""
    raw = [d.overall_score for d in dimensions if d.overall_score]
    numeric = [s for s in (parse_numeric_score(v) for v in raw) if s is not None]
    return round(sum(numeric) / len(numeric), 1) if numeric else None


def _compute_accumulated_scores(
    all_dimensions: list[DimensionResult], prev_run_latest: list[DimensionResult],
) -> tuple[float | None, float | None]:
    """Compute current and previous overall average scores."""
    return numeric_average(all_dimensions), (numeric_average(prev_run_latest) if prev_run_latest else None)


@dataclass(frozen=True)
class _AccumulatedResult:
    """Pre-computed parts for the accumulated response."""
    all_dimensions: list[DimensionResult]
    dimensions_with_trend: list[DimensionResult]
    severity: dict[str, int]
    avg_score: float | None
    prev_avg_score: float | None


def _build_accumulated_response(project: str, result: _AccumulatedResult) -> dict[str, Any]:
    """Assemble the final accumulated response dict."""
    return {
        "project": project,
        "dimensions": [to_camel_dict(d) for d in result.dimensions_with_trend],
        "summary": {
            "overallGrade": (
                score_to_grade_label(result.avg_score) if result.avg_score is not None
                else most_frequent_grade([d.overall_grade for d in result.all_dimensions if d.overall_grade])
            ),
            "numericAverage": result.avg_score,
            "previousNumericAverage": result.prev_avg_score,
            "totalViolations": result.severity["totalViolations"],
            "totalCompliance": result.severity["totalCompliance"],
            "dimensionCount": len(result.dimensions_with_trend),
            "severity": {
                "critical": result.severity["critical"],
                "major": result.severity["major"],
                "minor": result.severity["minor"],
            },
        },
    }
