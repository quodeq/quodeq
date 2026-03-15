from __future__ import annotations

from dataclasses import dataclass, field

from .finding import Finding, Totals
from .report import PrincipleGrade


@dataclass(frozen=True, slots=True)
class GradeBreakdown:
    grade: str
    count: int


@dataclass(frozen=True, slots=True)
class DimensionSummary:
    dimensions_count: int = 0
    overall_grade: str | None = None
    numeric_average: float | None = None
    grade_breakdown: list[GradeBreakdown] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DimensionResult:
    dimension: str
    overall_score: str | None = None
    overall_grade: str | None = None
    principles: list[PrincipleGrade] = field(default_factory=list)
    violations: list[Finding] = field(default_factory=list)
    compliance: list[Finding] = field(default_factory=list)
    totals: Totals | None = None
    source_file_count: int | None = None
    evidence_date: str | None = None
    discipline: str | None = None
    trend: str | None = None
    previous_run_id: str | None = None
    previous_score: str | None = None
    stale: bool = False
    from_run_id: str | None = None
    from_date_iso: str | None = None
    from_date_label: str | None = None
    run_id: str | None = None
