"""Mapper functions for dimension-result and dimension-summary dataclasses."""

from __future__ import annotations

from quodeq.core.types.dimension import DimensionResult, DimensionSummary, GradeBreakdown

from ._mapper_helpers import (
    get_bool,
    get_int,
    get_opt_float,
    get_opt_int,
    get_opt_str,
    get_str,
)
from ._mapper_findings import parse_finding_list
from ._mapper_reports import extract_totals, parse_principle_grades


def parse_dimension_result(raw: dict[str, object]) -> DimensionResult:
    """Parse a raw dict into a DimensionResult dataclass."""
    dim = raw.get("dimension")
    if not isinstance(dim, str):
        msg = f"DimensionResult.dimension must be str, got {type(dim).__name__}"
        raise TypeError(msg)

    principles = parse_principle_grades(raw)

    violations = parse_finding_list(raw.get("violations"))
    compliance = parse_finding_list(raw.get("compliance"))
    totals = extract_totals(raw)

    return DimensionResult(
        dimension=dim,
        overall_score=get_opt_str(raw.get("overallScore")),
        overall_grade=get_opt_str(raw.get("overallGrade")),
        principles=principles,
        violations=violations,
        compliance=compliance,
        totals=totals,
        source_file_count=get_opt_int(raw.get("sourceFileCount")),
        files_read=get_opt_int(raw.get("filesRead")),
        quarantined_count=get_opt_int(raw.get("quarantinedCount")) or 0,
        exit_reason=get_opt_str(raw.get("exitReason")),
        evidence_date=get_opt_str(raw.get("evidenceDate")),
        discipline=get_opt_str(raw.get("discipline")),
        trend=get_opt_str(raw.get("trend")),
        previous_run_id=get_opt_str(raw.get("previousRunId")),
        previous_score=get_opt_str(raw.get("previousScore")),
        stale=get_bool(raw, "stale"),
        from_run_id=get_opt_str(raw.get("fromRunId")),
        from_date_iso=get_opt_str(raw.get("fromDateIso")),
        from_date_label=get_opt_str(raw.get("fromDateLabel")),
        run_id=get_opt_str(raw.get("runId")),
    )


def parse_grade_breakdown(raw: dict[str, object]) -> GradeBreakdown:
    """Parse a raw dict into a GradeBreakdown dataclass."""
    return GradeBreakdown(
        grade=get_str(raw, "grade"),
        count=get_int(raw, "count"),
    )


def parse_dimension_summary(raw: dict[str, object]) -> DimensionSummary:
    """Parse a raw dict into a DimensionSummary dataclass."""
    gb_raw = raw.get("gradeBreakdown")
    grade_breakdown: list[GradeBreakdown] = []
    if isinstance(gb_raw, list):
        grade_breakdown = [parse_grade_breakdown(g) for g in gb_raw if isinstance(g, dict)]

    return DimensionSummary(
        dimensions_count=get_int(raw, "dimensionsCount"),
        overall_grade=get_opt_str(raw.get("overallGrade")),
        numeric_average=get_opt_float(raw.get("numericAverage")),
        grade_breakdown=grade_breakdown,
    )
