"""Mapper functions for project and job dataclasses."""

from __future__ import annotations

from quodeq.core.types.job import JobSnapshot
from quodeq.core.types.project import ProjectEntry, ProjectMetadata

from ._mapper_helpers import (
    get_int,
    get_opt_float,
    get_opt_int,
    get_opt_str,
    require_str,
    get_str,
)


def _project_identity_fields(raw: dict[str, object]) -> dict[str, str | None]:
    """The parent/display/discipline/path/location fields both project dataclasses carry."""
    return {
        "parent": get_opt_str(raw.get("parent")),
        "display_name": get_opt_str(raw.get("displayName")),
        "discipline": get_opt_str(raw.get("discipline")),
        "path": get_opt_str(raw.get("path")),
        "location": get_opt_str(raw.get("location")),
    }


def parse_project_metadata(raw: dict[str, object]) -> ProjectMetadata:
    """Parse a raw dict into a ProjectMetadata dataclass."""
    name = require_str(raw, "name", "ProjectMetadata")
    return ProjectMetadata(name=name, **_project_identity_fields(raw))


def parse_project_entry(raw: dict[str, object]) -> ProjectEntry:
    """Parse a raw dict into a ProjectEntry dataclass."""
    pid = require_str(raw, "id", "ProjectEntry")
    name = require_str(raw, "name", "ProjectEntry")
    return ProjectEntry(
        id=pid,
        name=name,
        **_project_identity_fields(raw),
        runs_count=get_int(raw, "runsCount"),
        latest_run_id=get_opt_str(raw.get("latestRunId")),
        latest_date=get_opt_str(raw.get("latestDate")),
        path_exists=raw.get("pathExists") if isinstance(raw.get("pathExists"), bool) else None,
        files_count=get_opt_int(raw.get("filesCount")),
        latest_grade=get_opt_str(raw.get("latestGrade")),
        latest_score=get_opt_float(raw.get("latestScore")),
    )


def parse_job_snapshot(raw: dict[str, object]) -> JobSnapshot:
    """Parse a raw dict into a JobSnapshot dataclass."""
    job_id = require_str(raw, "jobId", "JobSnapshot")
    status = require_str(raw, "status", "JobSnapshot")

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
        command=get_str(raw, "command"),
        started_at=get_str(raw, "startedAt"),
        ended_at=get_opt_str(raw.get("endedAt")),
        exit_code=get_opt_int(raw.get("exitCode")),
        logs=logs,
        output_project=get_opt_str(raw.get("outputProject")),
        output_run_id=get_opt_str(raw.get("outputRunId")),
        phase=get_opt_str(raw.get("phase")),
        current_dimension=get_opt_str(raw.get("currentDimension")),
        dimensions=dims,
        error=get_opt_str(raw.get("error")),
    )
