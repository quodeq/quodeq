"""Mapper functions for violation and progress dataclasses."""

from __future__ import annotations

from quodeq.core.types.finding import Finding
from quodeq.core.types.violation import (
    VIOLATION_SCHEMA_VERSION,
    ProgressInfo,
    ViolationFileEntry,
    ViolationResponse,
    ViolationSummary,
)

from ._mapper_findings import parse_finding
from ._mapper_helpers import (
    get_bool,
    get_int,
    require_str,
    get_str,
)


def _parse_progress_info(raw: dict[str, object]) -> ProgressInfo:
    return ProgressInfo(
        files_read=get_int(raw, "filesRead"),
        violation_count=get_int(raw, "violationCount") or get_int(raw, "violations"),
        compliance_count=get_int(raw, "complianceCount") or get_int(raw, "compliance"),
    )


def parse_violation_response(raw: dict[str, object]) -> ViolationResponse:
    """Parse a raw dict into a ViolationResponse dataclass."""
    dim = require_str(raw, "dimension", ViolationResponse.__name__)
    run_id = require_str(raw, "runId", ViolationResponse.__name__)
    project = require_str(raw, "project", ViolationResponse.__name__)

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
        partial=get_bool(raw, "partial"),
        progress=progress,
        schema_version=get_int(raw, "schemaVersion", VIOLATION_SCHEMA_VERSION),
    )


def _parse_violation_file_entry(raw: dict[str, object]) -> ViolationFileEntry:
    return ViolationFileEntry(
        path=get_str(raw, "path"),
        count=get_int(raw, "count"),
        critical=get_int(raw, "critical"),
        major=get_int(raw, "major"),
        minor=get_int(raw, "minor"),
    )


def parse_violation_summary(raw: dict[str, object]) -> ViolationSummary:
    """Parse a raw dict into a ViolationSummary dataclass."""
    files_raw = raw.get("files")
    files: list[ViolationFileEntry] = []
    if isinstance(files_raw, list):
        files = [_parse_violation_file_entry(f) for f in files_raw if isinstance(f, dict)]

    return ViolationSummary(
        total=get_int(raw, "total"),
        critical=get_int(raw, "critical"),
        major=get_int(raw, "major"),
        minor=get_int(raw, "minor"),
        files=files,
        schema_version=get_int(raw, "schemaVersion", VIOLATION_SCHEMA_VERSION),
    )
