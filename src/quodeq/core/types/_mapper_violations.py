"""Mapper functions for violation, progress, and trend dataclasses."""

from __future__ import annotations

from .dashboard import TrendPoint
from .finding import Finding
from .violation import ProgressInfo, ViolationFileEntry, ViolationResponse, ViolationSummary

from ._mapper_findings import parse_finding
from ._mapper_helpers import (
    _bool,
    _int,
    _opt_float,
    _opt_str,
    _require_str,
    _str,
)


def _parse_progress_info(raw: dict[str, object]) -> ProgressInfo:
    return ProgressInfo(
        files_read=_int(raw, "filesRead"),
        violation_count=_int(raw, "violationCount") or _int(raw, "violations"),
        compliance_count=_int(raw, "complianceCount") or _int(raw, "compliance"),
    )


def parse_violation_response(raw: dict[str, object]) -> ViolationResponse:
    dim = _require_str(raw, "dimension", "ViolationResponse")
    run_id = _require_str(raw, "runId", "ViolationResponse")
    project = _require_str(raw, "project", "ViolationResponse")

    violations_raw = raw.get("violations")
    violations: list[Finding] = []
    if isinstance(violations_raw, list):
        violations = [parse_finding(f) for f in violations_raw if isinstance(f, dict)]

    compliance_raw = raw.get("compliance")
    compliance: list[Finding] = []
    if isinstance(compliance_raw, list):
        compliance = [parse_finding(f) for f in compliance_raw if isinstance(f, dict)]

    progress_raw = raw.get("progress")
    progress = _parse_progress_info(progress_raw) if isinstance(progress_raw, dict) else None

    return ViolationResponse(
        dimension=dim,
        run_id=run_id,
        project=project,
        violations=violations,
        compliance=compliance,
        partial=_bool(raw, "partial"),
        progress=progress,
    )


def _parse_violation_file_entry(raw: dict[str, object]) -> ViolationFileEntry:
    return ViolationFileEntry(
        path=_str(raw, "path"),
        count=_int(raw, "count"),
        critical=_int(raw, "critical"),
        major=_int(raw, "major"),
        minor=_int(raw, "minor"),
    )


def parse_violation_summary(raw: dict[str, object]) -> ViolationSummary:
    files_raw = raw.get("files")
    files: list[ViolationFileEntry] = []
    if isinstance(files_raw, list):
        files = [_parse_violation_file_entry(f) for f in files_raw if isinstance(f, dict)]

    return ViolationSummary(
        total=_int(raw, "total"),
        critical=_int(raw, "critical"),
        major=_int(raw, "major"),
        minor=_int(raw, "minor"),
        files=files,
    )


def parse_trend_point(raw: dict[str, object]) -> TrendPoint:
    run_id = _require_str(raw, "runId", "TrendPoint")
    raw_dims = raw.get("dimensions")
    dims = tuple(raw_dims) if isinstance(raw_dims, list) else ()
    return TrendPoint(
        run_id=run_id,
        date_iso=_opt_str(raw.get("dateIso")),
        date_label=_str(raw, "dateLabel"),
        dimensions_count=_int(raw, "dimensionsCount"),
        dimensions=dims,
        accumulated_dimensions_count=_int(raw, "accumulatedDimensionsCount"),
        overall_grade=_opt_str(raw.get("overallGrade")),
        numeric_average=_opt_float(raw.get("numericAverage")),
    )
