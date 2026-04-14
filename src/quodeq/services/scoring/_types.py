"""Shared types for the unified scoring module."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScoredDimension:
    """A single dimension's score, grade, and violation summary.

    This is the unified shape returned by all scoring module functions.
    It replaces the ad-hoc dicts and partial DimensionResult overlays
    used by the old code.
    """
    dimension: str
    overall_score: float | None = None
    overall_grade: str | None = None
    violation_count: int = 0
    compliance_count: int = 0
    severity_critical: int = 0
    severity_major: int = 0
    severity_minor: int = 0
    trend: str | None = None          # "up", "down", "same", "none"
    previous_score: float | None = None
    previous_run_id: str | None = None
    from_run_id: str | None = None
    from_date_iso: str | None = None
    from_date_label: str | None = None
    from_project: str | None = None
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "dimension": self.dimension,
            "overallScore": f"{self.overall_score}/10" if self.overall_score is not None else None,
            "overallGrade": self.overall_grade,
            "totals": {
                "violationCount": self.violation_count,
                "complianceCount": self.compliance_count,
                "severity": {
                    "critical": self.severity_critical,
                    "major": self.severity_major,
                    "minor": self.severity_minor,
                },
            },
            "trend": self.trend,
            "previousScore": f"{self.previous_score}/10" if self.previous_score is not None else None,
            "previousRunId": self.previous_run_id,
            "fromRunId": self.from_run_id,
            "fromDateIso": self.from_date_iso,
            "fromDateLabel": self.from_date_label,
            "stale": self.stale,
        }
        if self.from_project is not None:
            d["fromProject"] = self.from_project
        return d


@dataclass(frozen=True, slots=True)
class AccumulatedSummary:
    """Summary stats for an accumulated view."""
    overall_grade: str | None = None
    numeric_average: float | None = None
    previous_numeric_average: float | None = None
    total_violations: int = 0
    total_compliance: int = 0
    dimension_count: int = 0
    severity_critical: int = 0
    severity_major: int = 0
    severity_minor: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "overallGrade": self.overall_grade,
            "numericAverage": self.numeric_average,
            "previousNumericAverage": self.previous_numeric_average,
            "totalViolations": self.total_violations,
            "totalCompliance": self.total_compliance,
            "dimensionCount": self.dimension_count,
            "severity": {
                "critical": self.severity_critical,
                "major": self.severity_major,
                "minor": self.severity_minor,
            },
        }


@dataclass(frozen=True, slots=True)
class TrendEntry:
    """A single point in the accumulated trend (one run)."""
    run_id: str
    date_iso: str | None = None
    date_label: str | None = None
    dimensions_count: int = 0
    dimensions: list[str] = field(default_factory=list)
    dimension_details: list[dict[str, Any]] = field(default_factory=list)
    accumulated_dimensions_count: int = 0
    run_numeric_average: float | None = None
    run_overall_grade: str | None = None
    numeric_average: float | None = None
    overall_grade: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "dateISO": self.date_iso,
            "dateLabel": self.date_label,
            "dimensionsCount": self.dimensions_count,
            "dimensions": self.dimensions,
            "dimensionDetails": self.dimension_details,
            "accumulatedDimensionsCount": self.accumulated_dimensions_count,
            "runNumericAverage": self.run_numeric_average,
            "runOverallGrade": self.run_overall_grade,
            "numericAverage": self.numeric_average,
            "overallGrade": self.overall_grade,
        }


@dataclass(frozen=True, slots=True)
class AccumulatedState:
    """Full accumulated response payload."""
    project: str
    dimensions: list[ScoredDimension] = field(default_factory=list)
    summary: AccumulatedSummary = field(default_factory=AccumulatedSummary)
    trend: list[TrendEntry] = field(default_factory=list)
    available_runs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accumulated": {
                "dimensions": [d.to_dict() for d in self.dimensions],
                "summary": self.summary.to_dict(),
            },
            "trend": [t.to_dict() for t in self.trend],
            "availableRuns": self.available_runs,
        }
