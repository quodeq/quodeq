"""Mapper functions for project and job dataclasses."""

from __future__ import annotations

from .job import JobSnapshot
from .project import ProjectEntry, ProjectMetadata

from ._mapper_helpers import (
    _int,
    _opt_float,
    _opt_int,
    _opt_str,
    _require_str,
    _str,
)


def parse_project_metadata(raw: dict[str, object]) -> ProjectMetadata:
    """Parse a raw dict into a ProjectMetadata dataclass."""
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
    """Parse a raw dict into a ProjectEntry dataclass."""
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
    """Parse a raw dict into a JobSnapshot dataclass."""
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
