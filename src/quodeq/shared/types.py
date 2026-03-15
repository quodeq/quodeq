"""Shared TypedDict definitions replacing dict[str, Any] across the codebase.

Import from here instead of using bare ``dict[str, Any]`` for well-known
data shapes.  This gives type checkers and readers a precise contract for
each dict.
"""
from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# Severity / Totals
# ---------------------------------------------------------------------------

class SeverityTally(TypedDict):
    """Counts per severity bucket."""
    critical: int
    major: int
    minor: int
    unknown: int


class TotalsDict(TypedDict):
    """Aggregate violation/compliance counts returned by ``build_totals``."""
    violationCount: int
    complianceCount: int
    severity: SeverityTally


# ---------------------------------------------------------------------------
# Grade breakdown
# ---------------------------------------------------------------------------

class GradeBreakdownEntry(TypedDict):
    """One row in the grade-breakdown list."""
    grade: str
    count: int


class DimensionSummary(TypedDict):
    """Summary across multiple dimension evaluation results."""
    dimensionsCount: int
    overallGrade: str | None
    numericAverage: float | None
    gradeBreakdown: list[GradeBreakdownEntry]


# ---------------------------------------------------------------------------
# Evidence metadata
# ---------------------------------------------------------------------------

class EvidenceFileMeta(TypedDict):
    """Metadata extracted from an ``_evidence.json`` file."""
    dimension: str
    sourceFileCount: int | None
    date: str | None
    discipline: str | None


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

class FindingDict(TypedDict, total=False):
    """Normalized finding dict produced by ``build_finding_base``.

    Fields marked ``total=False`` may be absent depending on the source
    (JSONL, evaluation JSON, stream).
    """
    principle: str | None
    file: str | None
    line: int | str | None
    title: str | None
    reason: str | None
    snippet: str | None
    severity: str
    cwe: int | str
    req: str
    req_refs: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Violation response (API)
# ---------------------------------------------------------------------------

class ViolationResponse(TypedDict, total=False):
    """Response dict from violation/compliance parsers."""
    dimension: str
    runId: str
    project: str
    violations: list[FindingDict]
    compliance: list[FindingDict]
    partial: bool
    progress: dict[str, int]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class ScaleInfo(TypedDict):
    """Project-size scaling tier info."""
    tier: str
    multiplier: int
    files_read: int


class ScoringResult(TypedDict):
    """Top-level dict returned by ``run_scoring``."""
    repository: str
    discipline: str
    date: str
    mode: str
    principles: dict[str, dict[str, object]]
    overall: dict[str, object]
    scale: ScaleInfo


# ---------------------------------------------------------------------------
# Principle grade (used in parsed reports)
# ---------------------------------------------------------------------------

class PrincipleGradeEntry(TypedDict):
    """One principle's name/score/grade from a parsed evaluation JSON."""
    name: str | None
    score: str | None
    grade: str | None


class PrincipleGradeWithOverall(TypedDict):
    """Principle grade entry extended with isOverall flag."""
    principle: str | None
    score: str | None
    grade: str | None
    isOverall: bool


# ---------------------------------------------------------------------------
# Parsed report
# ---------------------------------------------------------------------------

class ParsedReport(TypedDict):
    """Normalized report dict returned by ``parse_report_json``."""
    dimension: str | None
    overallScore: str | None
    overallGrade: str | None
    principles: list[PrincipleGradeEntry]
    detailPrinciples: list[object]
    violations: list[FindingDict]
    compliance: list[FindingDict]
    totals: TotalsDict


# ---------------------------------------------------------------------------
# Project entry (API)
# ---------------------------------------------------------------------------

class ProjectMetadata(TypedDict):
    """Normalized project metadata from repository_info.json."""
    name: str
    parent: str | None
    displayName: str | None
    discipline: str | None
    path: str | None
    location: str | None


class ProjectEntry(TypedDict, total=False):
    """Single project dict in the list_projects response."""
    id: str
    name: str
    parent: str | None
    displayName: str | None
    discipline: str | None
    path: str | None
    location: str | None
    runsCount: int
    latestRunId: str
    latestDate: str | None
    pathExists: bool | None
    filesCount: int | None
    latestGrade: str | None
    latestScore: float | None


class ProjectListResponse(TypedDict):
    """Response from list_projects."""
    projects: list[ProjectEntry]


# ---------------------------------------------------------------------------
# Job (serialized)
# ---------------------------------------------------------------------------

class JobDict(TypedDict, total=False):
    """Serialized job state returned by ``Job.to_dict``."""
    jobId: str
    status: str
    command: str
    startedAt: str
    endedAt: str | None
    exitCode: int | None
    logs: list[str]
    outputProject: str | None
    outputRunId: str | None
    phase: str | None
    currentDimension: str | None
    dimensions: list[str] | None


# ---------------------------------------------------------------------------
# Violation summary (aggregate)
# ---------------------------------------------------------------------------

class FileViolationEntry(TypedDict):
    """Per-file violation tally in the aggregate summary."""
    path: str
    count: int
    critical: int
    major: int
    minor: int


# ---------------------------------------------------------------------------
# Dimension run data (merged evaluation + evidence)
# ---------------------------------------------------------------------------

class DimensionData(TypedDict, total=False):
    """One dimension's merged evaluation + evidence data from a run.

    Returned by ``read_run_data`` and used throughout dashboard/accumulated.
    """
    dimension: str | None
    overallScore: str | None
    overallGrade: str | None
    principles: list[PrincipleGradeEntry]
    violations: list[FindingDict]
    compliance: list[FindingDict]
    totals: TotalsDict
    sourceFileCount: int | None
    evidenceDate: str | None
    discipline: str | None


class PreviousRunMatch(TypedDict):
    """Result of finding a dimension's data in a previous run."""
    runId: str
    dimension: DimensionData


class PluginDimensionEntry(TypedDict, total=False):
    """One dimension entry in a discovered plugin."""
    id: str
    weight: int | float
    iso_25010: str | None


class PluginInfo(TypedDict):
    """Discovered plugin metadata."""
    id: str
    name: str
    extensions: list[str]
    dimensions: list[PluginDimensionEntry]


class ViolationSummary(TypedDict, total=False):
    """Aggregated violation summary returned by ``aggregate_violations``."""
    total: int
    critical: int
    major: int
    minor: int
    files: list[FileViolationEntry]
