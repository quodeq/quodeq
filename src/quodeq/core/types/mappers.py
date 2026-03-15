"""Pure functions that convert raw dict[str, object] to frozen dataclasses."""

from __future__ import annotations

from .dashboard import TrendPoint
from .dimension import DimensionResult, DimensionSummary, GradeBreakdown
from .evidence import EvidenceFileMeta
from .finding import Finding, ReqRef, SeverityTally, Totals
from .job import JobSnapshot
from .plugin import PluginDimension, PluginInfo
from .project import ProjectEntry, ProjectMetadata
from .report import ParsedReport, PrincipleGrade
from .violation import ProgressInfo, ViolationFileEntry, ViolationResponse, ViolationSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opt_str(v: object) -> str | None:
    return v if isinstance(v, str) else None


def _opt_int(v: object) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _opt_float(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def _opt_str_or_int(v: object) -> int | str | None:
    if isinstance(v, bool):
        return None
    return v if isinstance(v, (str, int)) else None


def _str(raw: dict[str, object], key: str, default: str = "") -> str:
    v = raw.get(key, default)
    return v if isinstance(v, str) else default


def _int(raw: dict[str, object], key: str, default: int = 0) -> int:
    v = raw.get(key, default)
    if isinstance(v, bool):
        return default
    return v if isinstance(v, int) else default


def _float(raw: dict[str, object], key: str, default: float = 0.0) -> float:
    v = raw.get(key, default)
    if isinstance(v, bool):
        return default
    return float(v) if isinstance(v, (int, float)) else default


def _bool(raw: dict[str, object], key: str, default: bool = False) -> bool:
    v = raw.get(key, default)
    return v if isinstance(v, bool) else default


def _str_list(raw: dict[str, object], key: str) -> list[str]:
    v = raw.get(key)
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str)]


# ---------------------------------------------------------------------------
# Mappers
# ---------------------------------------------------------------------------


def parse_req_ref(raw: dict[str, object]) -> ReqRef:
    return ReqRef(
        label=_str(raw, "label"),
        url=_str(raw, "url"),
    )


def parse_finding(raw: dict[str, object]) -> Finding:
    req_refs_raw = raw.get("reqRefs")
    req_refs: list[ReqRef] = []
    if isinstance(req_refs_raw, list):
        req_refs = [parse_req_ref(r) for r in req_refs_raw if isinstance(r, dict)]

    return Finding(
        principle=_opt_str(raw.get("principle")),
        file=_opt_str(raw.get("file")),
        line=_opt_str_or_int(raw.get("line")),
        title=_opt_str(raw.get("title")),
        reason=_opt_str(raw.get("reason")),
        snippet=_opt_str(raw.get("snippet")),
        severity=_str(raw, "severity", "minor"),
        cwe=_opt_str_or_int(raw.get("cwe")),
        req=_opt_str(raw.get("req")),
        req_refs=req_refs,
        dimension=_opt_str(raw.get("dimension")),
        violation_type=_opt_str(raw.get("violationType")),
    )


def parse_severity_tally(raw: dict[str, object]) -> SeverityTally:
    return SeverityTally(
        critical=_int(raw, "critical"),
        major=_int(raw, "major"),
        minor=_int(raw, "minor"),
        unknown=_int(raw, "unknown"),
    )


def parse_totals(raw: dict[str, object]) -> Totals:
    sev_raw = raw.get("severity")
    severity = parse_severity_tally(sev_raw) if isinstance(sev_raw, dict) else SeverityTally()
    return Totals(
        violation_count=_int(raw, "violationCount"),
        compliance_count=_int(raw, "complianceCount"),
        severity=severity,
    )


def parse_principle_grade(raw: dict[str, object]) -> PrincipleGrade:
    return PrincipleGrade(
        name=_opt_str(raw.get("name")),
        score=_opt_str(raw.get("score")),
        grade=_opt_str(raw.get("grade")),
    )


def parse_parsed_report(raw: dict[str, object]) -> ParsedReport:
    principles_raw = raw.get("principles")
    principles: list[PrincipleGrade] = []
    if isinstance(principles_raw, list):
        principles = [parse_principle_grade(p) for p in principles_raw if isinstance(p, dict)]

    violations_raw = raw.get("violations")
    violations: list[Finding] = []
    if isinstance(violations_raw, list):
        violations = [parse_finding(f) for f in violations_raw if isinstance(f, dict)]

    compliance_raw = raw.get("compliance")
    compliance: list[Finding] = []
    if isinstance(compliance_raw, list):
        compliance = [parse_finding(f) for f in compliance_raw if isinstance(f, dict)]

    detail_raw = raw.get("detailPrinciples")
    detail_principles: list[object] = []
    if isinstance(detail_raw, list):
        detail_principles = list(detail_raw)

    totals_raw = raw.get("totals")
    totals = parse_totals(totals_raw) if isinstance(totals_raw, dict) else None

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

    violations_raw = raw.get("violations")
    violations: list[Finding] = []
    if isinstance(violations_raw, list):
        violations = [parse_finding(f) for f in violations_raw if isinstance(f, dict)]

    compliance_raw = raw.get("compliance")
    compliance: list[Finding] = []
    if isinstance(compliance_raw, list):
        compliance = [parse_finding(f) for f in compliance_raw if isinstance(f, dict)]

    totals_raw = raw.get("totals")
    totals = parse_totals(totals_raw) if isinstance(totals_raw, dict) else None

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


def parse_project_metadata(raw: dict[str, object]) -> ProjectMetadata:
    name = raw.get("name")
    if not isinstance(name, str):
        msg = f"ProjectMetadata.name must be str, got {type(name).__name__}"
        raise TypeError(msg)
    return ProjectMetadata(
        name=name,
        parent=_opt_str(raw.get("parent")),
        display_name=_opt_str(raw.get("displayName")),
        discipline=_opt_str(raw.get("discipline")),
        path=_opt_str(raw.get("path")),
        location=_opt_str(raw.get("location")),
    )


def parse_project_entry(raw: dict[str, object]) -> ProjectEntry:
    pid = raw.get("id")
    if not isinstance(pid, str):
        msg = f"ProjectEntry.id must be str, got {type(pid).__name__}"
        raise TypeError(msg)
    name = raw.get("name")
    if not isinstance(name, str):
        msg = f"ProjectEntry.name must be str, got {type(name).__name__}"
        raise TypeError(msg)
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
    job_id = raw.get("jobId")
    if not isinstance(job_id, str):
        msg = f"JobSnapshot.jobId must be str, got {type(job_id).__name__}"
        raise TypeError(msg)
    status = raw.get("status")
    if not isinstance(status, str):
        msg = f"JobSnapshot.status must be str, got {type(status).__name__}"
        raise TypeError(msg)

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
    pid = raw.get("id")
    if not isinstance(pid, str):
        msg = f"PluginDimension.id must be str, got {type(pid).__name__}"
        raise TypeError(msg)
    return PluginDimension(
        id=pid,
        weight=_int(raw, "weight", 1),
        iso_25010=_opt_str(raw.get("iso_25010")),
    )


def parse_plugin_info(raw: dict[str, object]) -> PluginInfo:
    pid = raw.get("id")
    if not isinstance(pid, str):
        msg = f"PluginInfo.id must be str, got {type(pid).__name__}"
        raise TypeError(msg)
    name = raw.get("name")
    if not isinstance(name, str):
        msg = f"PluginInfo.name must be str, got {type(name).__name__}"
        raise TypeError(msg)

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
        violations=_int(raw, "violations"),
        compliance=_int(raw, "compliance"),
    )


def parse_violation_response(raw: dict[str, object]) -> ViolationResponse:
    dim = raw.get("dimension")
    if not isinstance(dim, str):
        msg = f"ViolationResponse.dimension must be str, got {type(dim).__name__}"
        raise TypeError(msg)
    run_id = raw.get("runId")
    if not isinstance(run_id, str):
        msg = f"ViolationResponse.runId must be str, got {type(run_id).__name__}"
        raise TypeError(msg)
    project = raw.get("project")
    if not isinstance(project, str):
        msg = f"ViolationResponse.project must be str, got {type(project).__name__}"
        raise TypeError(msg)

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
    run_id = raw.get("runId")
    if not isinstance(run_id, str):
        msg = f"TrendPoint.runId must be str, got {type(run_id).__name__}"
        raise TypeError(msg)
    return TrendPoint(
        run_id=run_id,
        date_iso=_opt_str(raw.get("dateIso")),
        date_label=_str(raw, "dateLabel"),
        dimensions_count=_int(raw, "dimensionsCount"),
        overall_grade=_opt_str(raw.get("overallGrade")),
        numeric_average=_opt_float(raw.get("numericAverage")),
    )
