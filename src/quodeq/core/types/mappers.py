"""Pure functions that convert raw dict[str, object] to frozen dataclasses.

Dimension-related parsers live here; everything else is split into peer modules
and re-exported so that ``from quodeq.core.types.mappers import X`` keeps working.
"""

from __future__ import annotations

from .dimension import DimensionResult, DimensionSummary, GradeBreakdown
from .evidence import EvidenceFileMeta
from .finding import Totals
from .report import ParsedReport, PrincipleGrade

from ._mapper_helpers import (
    _bool,
    _int,
    _opt_float,
    _opt_int,
    _opt_str,
    _str,
)
from ._mapper_findings import (
    _parse_finding_list,
    parse_finding,
    parse_req_ref,
    parse_severity_tally,
    parse_totals,
)
from ._mapper_entities import (
    _parse_progress_info,
    _parse_violation_file_entry,
    parse_job_snapshot,
    parse_plugin_dimension,
    parse_plugin_info,
    parse_project_entry,
    parse_project_metadata,
    parse_trend_point,
    parse_violation_response,
    parse_violation_summary,
)


# ---------------------------------------------------------------------------
# Dimension-related parsers (kept in this file)
# ---------------------------------------------------------------------------


def _extract_totals(raw: dict[str, object]) -> Totals | None:
    """Parse a 'totals' field that may be a Totals instance, a raw dict, or absent."""
    totals_raw = raw.get("totals")
    if isinstance(totals_raw, Totals):
        return totals_raw
    if isinstance(totals_raw, dict):
        return parse_totals(totals_raw)
    return None


def parse_principle_grade(raw: dict[str, object]) -> PrincipleGrade:
    return PrincipleGrade(
        principle=_opt_str(raw.get("name")) or _opt_str(raw.get("principle")),
        score=_opt_str(raw.get("score")),
        grade=_opt_str(raw.get("grade")),
    )


def parse_parsed_report(raw: dict[str, object]) -> ParsedReport:
    principles_raw = raw.get("principles")
    principles: list[PrincipleGrade] = []
    if isinstance(principles_raw, list):
        principles = [parse_principle_grade(p) for p in principles_raw if isinstance(p, dict)]

    violations = _parse_finding_list(raw.get("violations"))
    compliance = _parse_finding_list(raw.get("compliance"))

    detail_raw = raw.get("detailPrinciples")
    detail_principles: list[dict[str, object]] = []
    if isinstance(detail_raw, list):
        detail_principles = list(detail_raw)

    totals = _extract_totals(raw)

    return ParsedReport(
        dimension=_opt_str(raw.get("dimension")),
        overall_score=_opt_str(raw.get("overallScore")),
        overall_grade=_opt_str(raw.get("overallGrade")),
        principles=principles,
        detail_principles=detail_principles,
        violations=violations,
        compliance=compliance,
        totals=totals,
    )


def parse_evidence_file_meta(raw: dict[str, object]) -> EvidenceFileMeta:
    dim = raw.get("dimension")
    if not isinstance(dim, str):
        msg = f"EvidenceFileMeta.dimension must be str, got {type(dim).__name__}"
        raise TypeError(msg)
    return EvidenceFileMeta(
        dimension=dim,
        source_file_count=_opt_int(raw.get("sourceFileCount")),
        date=_opt_str(raw.get("date")),
        discipline=_opt_str(raw.get("discipline")),
    )


def parse_dimension_result(raw: dict[str, object]) -> DimensionResult:
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
    return GradeBreakdown(
        grade=_str(raw, "grade"),
        count=_int(raw, "count"),
    )


def parse_dimension_summary(raw: dict[str, object]) -> DimensionSummary:
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


# ---------------------------------------------------------------------------
# Re-export everything so existing imports keep working
# ---------------------------------------------------------------------------

__all__ = [
    # findings
    "parse_finding",
    "parse_req_ref",
    "parse_severity_tally",
    "parse_totals",
    # dimensions (defined here)
    "parse_dimension_result",
    "parse_dimension_summary",
    "parse_evidence_file_meta",
    "parse_grade_breakdown",
    "parse_parsed_report",
    "parse_principle_grade",
    # entities
    "parse_job_snapshot",
    "parse_plugin_dimension",
    "parse_plugin_info",
    "parse_project_entry",
    "parse_project_metadata",
    "parse_trend_point",
    "parse_violation_response",
    "parse_violation_summary",
]
