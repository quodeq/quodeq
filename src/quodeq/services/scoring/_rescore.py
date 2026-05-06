"""Rescore dimensions with dismissals applied.

Reuses the SAME scoring engine as the original evaluation, including
the 4-stage formula. This module delegates to the existing
``services.rescore`` module for the actual computation, and converts
the result into our typed ScoredDimension objects.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.rescore import rescore_dimensions as _raw_rescore
from quodeq.services.scoring._run_scores import get_run_dimensions, parse_score
from quodeq.services.scoring._types import ScoredDimension


def _dim_result_to_scored(d: dict, from_run_id: str | None = None, from_project: str | None = None) -> ScoredDimension:
    """Convert a camelCase dict (from rescore_dimensions) to ScoredDimension."""
    totals = d.get("totals", {})
    severity = totals.get("severity", {})
    return ScoredDimension(
        dimension=d.get("dimension", ""),
        overall_score=parse_score(d.get("overallScore")),
        overall_grade=d.get("overallGrade"),
        violation_count=totals.get("violationCount", 0),
        compliance_count=totals.get("complianceCount", 0),
        severity_critical=severity.get("critical", 0),
        severity_major=severity.get("major", 0),
        severity_minor=severity.get("minor", 0),
        from_run_id=from_run_id,
        from_project=from_project,
    )


def rescore_run(
    reports_root: Path, project: str, run_id: str,
) -> list[ScoredDimension]:
    """Rescore all dimensions in a run with current dismissals applied.

    Returns typed ScoredDimension objects with rescored scores.
    """
    dimensions = get_run_dimensions(reports_root, project, run_id)
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        return _dims_to_scored(dimensions, run_id)

    result = _raw_rescore(dimensions, dismissed, deleted)
    return [
        _dim_result_to_scored(d, from_run_id=run_id)
        for d in result.get("dimensions", [])
    ]


def rescore_run_raw(
    reports_root: Path, project: str, run_id: str,
) -> dict:
    """Return the raw rescore dict (for backward compat with explorer detail).

    Returns the same shape as the old /api/rescore endpoint.
    """
    dimensions = get_run_dimensions(reports_root, project, run_id)
    project_dir = reports_root / project
    dismissed = dismissed_keys(project_dir)
    deleted = deleted_keys(project_dir)
    if not dismissed and not deleted:
        from quodeq.data.fs.report_parser.grades import summarize_dimensions
        from quodeq.core.types import to_camel_dict
        return {
            "dimensions": [to_camel_dict(d) for d in dimensions],
            "summary": to_camel_dict(summarize_dimensions(dimensions)),
        }
    return _raw_rescore(dimensions, dismissed, deleted)


def _dims_to_scored(
    dimensions: list[DimensionResult], run_id: str,
) -> list[ScoredDimension]:
    """Convert raw DimensionResult objects to ScoredDimension (no dismissals)."""
    result = []
    for d in dimensions:
        totals = d.totals
        result.append(ScoredDimension(
            dimension=d.dimension or "",
            overall_score=parse_score(d.overall_score),
            overall_grade=d.overall_grade,
            violation_count=totals.violation_count if totals else 0,
            compliance_count=totals.compliance_count if totals else 0,
            severity_critical=totals.severity.critical if totals else 0,
            severity_major=totals.severity.major if totals else 0,
            severity_minor=totals.severity.minor if totals else 0,
            from_run_id=run_id,
        ))
    return result
