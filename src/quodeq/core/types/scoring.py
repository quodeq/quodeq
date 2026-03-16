from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_GRADE = "Critical"


@dataclass(frozen=True, slots=True)
class ScaleInfo:
    tier: str
    multiplier: int
    files_read: int


@dataclass(frozen=True, slots=True)
class Deductions:
    critical_type_count: int = 0
    major_type_count: int = 0
    minor_type_count: int = 0
    critical_deduction: float = 0.0
    major_deduction: float = 0.0
    minor_deduction: float = 0.0
    total_deduction: float = 0.0
    critical_cap: float = 0.0
    major_cap: float = 0.0


@dataclass(frozen=True, slots=True)
class PrincipleScore:
    display_name: str
    weight: str = "1"
    compliance_percentage: float = 0.0
    taxonomy_used: bool = False
    confidence_level: str = "low"
    confidence_interval: float = 0.0
    grade_stability: str = "unstable"
    base_score: int = 0
    deductions: Deductions | None = None
    dampening_multiplier: float | None = None
    final_score: float | None = None
    grade: str = _DEFAULT_GRADE
    base_grade: str | None = None
    severity_drops: int | None = None


@dataclass(frozen=True, slots=True)
class OverallScore:
    weighted_score: float | None = None
    weighted_grade: str | None = None
    grade: str | None = None
    total_weight: int = 0
    confidence: str | None = None
    confidence_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ScoringResult:
    repository: str
    discipline: str
    date: str
    mode: str
    principles: dict[str, PrincipleScore] = field(default_factory=dict)
    overall: OverallScore | None = None
    scale: ScaleInfo | None = None
