from __future__ import annotations

from dataclasses import dataclass, field

from .finding import Finding, Totals


@dataclass(frozen=True, slots=True)
class PrincipleGrade:
    name: str | None = None
    score: str | None = None
    grade: str | None = None


@dataclass(frozen=True, slots=True)
class PrincipleGradeWithOverall:
    principle: str | None = None
    score: str | None = None
    grade: str | None = None
    is_overall: bool = False


@dataclass(frozen=True, slots=True)
class ParsedReport:
    dimension: str | None = None
    overall_score: str | None = None
    overall_grade: str | None = None
    principles: list[PrincipleGrade] = field(default_factory=list)
    detail_principles: list[object] = field(default_factory=list)
    violations: list[Finding] = field(default_factory=list)
    compliance: list[Finding] = field(default_factory=list)
    totals: Totals | None = None
