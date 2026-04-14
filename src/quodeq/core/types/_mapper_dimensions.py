"""Mapper functions for dimension-result and dimension-summary dataclasses."""

from __future__ import annotations

from .dimension import DimensionResult, DimensionSummary, GradeBreakdown
from .report import PrincipleGrade

from ._mapper_helpers import (
    _bool,
    _int,
    _opt_float,
    _opt_int,
    _opt_str,
    _str,
)
from ._mapper_findings import _parse_finding_list
from ._mapper_reports import _extract_totals, parse_principle_grade


def parse_dimension_result(raw: dict[str, object]) -> DimensionResult:
    """Parse a raw dict into a DimensionResult dataclass."""
    dim = raw.get("dimension")
    if not isinstance(dim, str):
        msg = f"DimensionResult.dimension must be str, got {type(dim).__name__}"
        raise TypeError(msg)

    principles_raw = raw.get("principles")
    principles: list[PrincipleGrade] = []
    if isinstance(principles_raw, list):
        principles = [parse_principle_grade(p) for p in principles_raw if isinstance(p, dict)]

    violations = _parse_finding_list(raw.get("violations"))
    compliance = _parse_finding_list(raw.get("compliance"))
    totals = _extract_totals(raw)

    return DimensionResult(
        dimension=dim,
        overall_score=_opt_str(raw.get("overallScore")),
        overall_grade=_opt_str(raw.get("overallGrade")),
        principles=principles,
        violations=violations,
        compliance=compliance,
        totals=totals,
        source_file_count=_opt_int(raw.get("sourceFileCount")),
        evidence_date=_opt_str(raw.get("evidenceDate")),
        discipline=_opt_str(raw.get("discipline")),
        trend=_opt_str(raw.get("trend")),
        previous_run_id=_opt_str(raw.get("previousRunId")),
        previous_score=_opt_str(raw.get("previousScore")),
        stale=_bool(raw, "stale"),
        from_run_id=_opt_str(raw.get("fromRunId")),
        from_date_iso=_opt_str(raw.get("fromDateIso")),
        from_date_label=_opt_str(raw.get("fromDateLabel")),
        run_id=_opt_str(raw.get("runId")),
    )


def parse_grade_breakdown(raw: dict[str, object]) -> GradeBreakdown:
    """Parse a raw dict into a GradeBreakdown dataclass."""
    return GradeBreakdown(
        grade=_str(raw, "grade"),
        count=_int(raw, "count"),
    )


def parse_dimension_summary(raw: dict[str, object]) -> DimensionSummary:
    """Parse a raw dict into a DimensionSummary dataclass."""
    gb_raw = raw.get("gradeBreakdown")
    grade_breakdown: list[GradeBreakdown] = []
    if isinstance(gb_raw, list):
        grade_breakdown = [parse_grade_breakdown(g) for g in gb_raw if isinstance(g, dict)]

    return DimensionSummary(
        dimensions_count=_int(raw, "dimensionsCount"),
        overall_grade=_opt_str(raw.get("overallGrade")),
        numeric_average=_opt_float(raw.get("numericAverage")),
        grade_breakdown=grade_breakdown,
    )
