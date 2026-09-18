"""Everything ``core.scoring`` returns: the per-principle scores and their roll-up."""
from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_GRADE = "Critical"


@dataclass(frozen=True, slots=True)
class ScaleInfo:
    """The project-size tier scoring used, and the file counts it was derived from.

    Set by ``core.scoring.engine.run_scoring``; the multiplier is what scales
    the per-severity deduction caps for a large codebase.
    """

    tier: str
    multiplier: int
    files_read: int


@dataclass(frozen=True, slots=True)
class Deductions:
    """Numerical-mode penalty breakdown from ``core.scoring.numerical.build_deductions``.

    Kept on the principle score so the UI can show how a grade was reached
    rather than just the number.
    """

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
    """One principle's grade plus the inputs that explain it.

    Produced per principle by ``core.scoring._principle``. Which optional
    fields are filled depends on the mode: numerical sets ``base_score``,
    ``deductions`` and ``final_score``, graded sets ``base_grade`` and
    ``severity_drops``. Only ``grade`` is set by both.
    """

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
    """Weight-averaged roll-up of the principle scores, from ``weighted_overall``.

    Numerical mode fills ``weighted_score``/``grade``, graded mode fills
    ``weighted_grade``; ``confidence_reason`` names what held the confidence
    down so the UI does not have to guess.
    """

    weighted_score: float | None = None
    weighted_grade: str | None = None
    grade: str | None = None
    total_weight: int = 0
    confidence: str | None = None
    confidence_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ScoringResult:
    """The complete output of scoring one evidence file.

    Returned by ``core.scoring.engine.run_scoring``; the repository,
    discipline and date are copied off the evidence so the result stands on
    its own once written to a report.
    """

    repository: str
    discipline: str
    date: str
    mode: str
    principles: dict[str, PrincipleScore] = field(default_factory=dict)
    overall: OverallScore | None = None
    scale: ScaleInfo | None = None
