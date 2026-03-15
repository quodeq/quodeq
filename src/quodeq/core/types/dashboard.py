from __future__ import annotations

from dataclasses import dataclass, field

from .dimension import GradeBreakdown


@dataclass(frozen=True, slots=True)
class TrendPoint:
    run_id: str
    date_iso: str | None = None
    date_label: str = ""
    dimensions_count: int = 0
    overall_grade: str | None = None
    numeric_average: float | None = None


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    dimensions_count: int = 0
    overall_grade: str | None = None
    numeric_average: float | None = None
    grade_breakdown: list[GradeBreakdown] = field(default_factory=list)
    date_iso: str | None = None
    date_label: str = ""


@dataclass(frozen=True, slots=True)
class AccumulatedSummary:
    overall_grade: str | None = None
    numeric_average: float | None = None
    previous_numeric_average: float | None = None
    total_violations: int = 0
    total_compliance: int = 0
    dimension_count: int = 0
    severity_critical: int = 0
    severity_major: int = 0
    severity_minor: int = 0
