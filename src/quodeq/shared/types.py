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
