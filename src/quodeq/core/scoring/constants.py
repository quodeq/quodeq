"""Scoring constants, lookup tables, and project-size scaling."""
from __future__ import annotations

from enum import StrEnum

from quodeq.core.types.severity import Severity

# ---------------------------------------------------------------------------
# Violation severity weights (for weighted violation count)
# ---------------------------------------------------------------------------
SEVERITY_WEIGHT: dict[str, float] = {Severity.CRITICAL: 4.0, Severity.MAJOR: 1.5, Severity.MINOR: 0.25}

# Top of the score scale; an int so caps built from it keep their type.
MAX_SCORE = 10

# Base score curve: base = 10 / (1 + K * weighted_violations)
BASE_K: float = 0.12

# Compliance lift curve compress exponent
LIFT_COMPRESS: float = 1.8

# Violation ceiling scale factor
CEIL_SCALE: float = 0.5

# Severity grade floor: minimum score by worst severity present
SEVERITY_GRADE_FLOOR: dict[str, float] = {
    Severity.CRITICAL: 0.0,
    Severity.MAJOR: 5.0,
    Severity.MINOR: 8.0,
}

# Legacy dampening constants
MAX_PENALTY_MULTIPLIER: float = 1.30
RATIO_DAMPENING_TABLE: list[tuple[float, float]] = [
    (3.0, 0.85),
    (2.0, 0.90),
    (1.0, 0.95),
    (0.5, 1.00),
    (0.0, 1.15),
    (-1.0, MAX_PENALTY_MULTIPLIER),
]


class Grade(StrEnum):
    """The grade labels the numeric score scale maps onto.

    The member value is the label written to reports, the grade tables and
    every API response, so renaming one rewrites stored history.
    """

    EXEMPLARY = "Exemplary"
    GOOD = "Good"
    ADEQUATE = "Adequate"
    POOR = "Poor"
    INSUFFICIENT = "Insufficient"


# Canonical ordering from worst to best for the qualitative ("text") mode,
# which `drop_grade` and the weighted-grade aggregation index into. Distinct
# from `Grade`: "Developing" and "Proficient" exist only on this ladder and
# no code path produces them from a numeric score.
GRADE_LADDER: list[str] = [
    Grade.INSUFFICIENT,
    "Developing",
    "Proficient",
    Grade.EXEMPLARY,
]

GRADE_THRESHOLDS: list[tuple[int, Grade]] = [
    (9, Grade.EXEMPLARY),
    (7, Grade.GOOD),
    (5, Grade.ADEQUATE),
    (3, Grade.POOR),
]

# ---------------------------------------------------------------------------
# Project-size scaling
# ---------------------------------------------------------------------------
SCALE_TIERS: list[tuple[int, int]] = [
    (100_000, 6),
    (50_000, 5),
    (20_000, 4),
    (5_000, 3),
    (500, 2),
    (0, 1),
]

SCALE_TIER_NAMES: dict[int, str] = {
    1: "Small",
    2: "Medium",
    3: "Large",
    4: "XLarge",
    5: "XXLarge",
    6: "Enterprise",
}

# Weight parsing constants
WEIGHT_TRIPLE: str = "x3"
WEIGHT_DOUBLE: str = "x2"


def scale_multiplier(source_file_count: int) -> int:
    """Return the size-based scaling multiplier for a project."""
    for threshold, multiplier in SCALE_TIERS:
        if source_file_count >= threshold:
            return multiplier
    return 1
