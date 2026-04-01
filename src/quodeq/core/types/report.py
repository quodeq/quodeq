from __future__ import annotations

from dataclasses import dataclass, field

from .finding import Finding, Totals


@dataclass(frozen=True, slots=True)
class PrincipleGrade:
    """Grade result for a single principle within a dimension report."""

    principle: str | None = None
    score: str | None = None
    grade: str | None = None


@dataclass(frozen=True, slots=True)
class PrincipleGradeWithOverall:
    """PrincipleGrade extended with an ``is_overall`` flag for aggregate rows."""

    principle: str | None = None
    score: str | None = None
    grade: str | None = None
    is_overall: bool = False


@dataclass(frozen=True, slots=True)
class ParsedReport:
    """Fully parsed dimension report with grades, findings, and totals."""

    dimension: str | None = None
    overall_score: str | None = None
    overall_grade: str | None = None
    principles: list[PrincipleGrade] = field(default_factory=list)
    detail_principles: list[dict[str, object]] = field(default_factory=list)
    violations: list[Finding] = field(default_factory=list)
    compliance: list[Finding] = field(default_factory=list)
    totals: Totals | None = None
