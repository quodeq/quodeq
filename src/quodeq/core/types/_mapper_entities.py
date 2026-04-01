"""Mapper functions for project, job, plugin, violation, and trend dataclasses."""

from __future__ import annotations

from .dashboard import TrendPoint
from .finding import Finding
from .job import JobSnapshot
from .plugin import PluginDimension, PluginInfo
from .project import ProjectEntry, ProjectMetadata
from .violation import ProgressInfo, ViolationFileEntry, ViolationResponse, ViolationSummary

from ._mapper_findings import parse_finding
from ._mapper_helpers import (
    _bool,
    _int,
    _opt_float,
    _opt_int,
    _opt_str,
    _str,
    _str_list,
)


def _require_str(raw: dict[str, object], field_name: str, context: str = "") -> str:
    """Return raw[field_name] as str, or raise TypeError with a descriptive message."""
    value = raw.get(field_name)
    if not isinstance(value, str):
        prefix = f"{context}." if context else ""
        msg = f"{prefix}{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def parse_project_metadata(raw: dict[str, object]) -> ProjectMetadata:
    name = _require_str(raw, "name", "ProjectMetadata")
    return ProjectMetadata(
        name=name,
        parent=_opt_str(raw.get("parent")),
        display_name=_opt_str(raw.get("displayName")),
        discipline=_opt_str(raw.get("discipline")),
        path=_opt_str(raw.get("path")),
        location=_opt_str(raw.get("location")),
    )


def parse_project_entry(raw: dict[str, object]) -> ProjectEntry:
    pid = _require_str(raw, "id", "ProjectEntry")
    name = _require_str(raw, "name", "ProjectEntry")
    return ProjectEntry(
        id=pid,
        name=name,
        parent=_opt_str(raw.get("parent")),
        display_name=_opt_str(raw.get("displayName")),
        discipline=_opt_str(raw.get("discipline")),
        path=_opt_str(raw.get("path")),
        location=_opt_str(raw.get("location")),
        runs_count=_int(raw, "runsCount"),
        latest_run_id=_opt_str(raw.get("latestRunId")),
        latest_date=_opt_str(raw.get("latestDate")),
        path_exists=raw.get("pathExists") if isinstance(raw.get("pathExists"), bool) else None,
        files_count=_opt_int(raw.get("filesCount")),
        latest_grade=_opt_str(raw.get("latestGrade")),
        latest_score=_opt_float(raw.get("latestScore")),
    )


def parse_job_snapshot(raw: dict[str, object]) -> JobSnapshot:
    job_id = _require_str(raw, "jobId", "JobSnapshot")
    status = _require_str(raw, "status", "JobSnapshot")

    logs_raw = raw.get("logs")
    logs: list[str] = []
    if isinstance(logs_raw, list):
        logs = [x for x in logs_raw if isinstance(x, str)]

    dims_raw = raw.get("dimensions")
    dims: list[str] | None = None
    if isinstance(dims_raw, list):
        dims = [x for x in dims_raw if isinstance(x, str)]

    return JobSnapshot(
        job_id=job_id,
        status=status,
        command=_str(raw, "command"),
        started_at=_str(raw, "startedAt"),
        ended_at=_opt_str(raw.get("endedAt")),
        exit_code=_opt_int(raw.get("exitCode")),
        logs=logs,
        output_project=_opt_str(raw.get("outputProject")),
        output_run_id=_opt_str(raw.get("outputRunId")),
        phase=_opt_str(raw.get("phase")),
        current_dimension=_opt_str(raw.get("currentDimension")),
        dimensions=dims,
        error=_opt_str(raw.get("error")),
    )


def parse_plugin_dimension(raw: dict[str, object]) -> PluginDimension:
    pid = _require_str(raw, "id", "PluginDimension")
    return PluginDimension(
        id=pid,
        weight=_int(raw, "weight", 1),
        iso_25010=_opt_str(raw.get("iso_25010")),
    )


def parse_plugin_info(raw: dict[str, object]) -> PluginInfo:
    pid = _require_str(raw, "id", "PluginInfo")
    name = _require_str(raw, "name", "PluginInfo")

    dims_raw = raw.get("dimensions")
    dims: list[PluginDimension] = []
    if isinstance(dims_raw, list):
        dims = [parse_plugin_dimension(d) for d in dims_raw if isinstance(d, dict)]

    return PluginInfo(
        id=pid,
        name=name,
        extensions=_str_list(raw, "extensions"),
        dimensions=dims,
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
