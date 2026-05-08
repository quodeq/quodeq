"""Scoring constants, lookup tables, and project-size scaling."""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Violation severity weights (for weighted violation count)
# ---------------------------------------------------------------------------
_SEVERITY_WEIGHT: dict[str, float] = {"critical": 4.0, "major": 1.5, "minor": 0.25}

# Base score curve: base = 10 / (1 + K * weighted_violations)
_BASE_K: float = 0.12

# Compliance lift curve compress exponent
_LIFT_COMPRESS: float = 1.8

# Violation ceiling scale factor
_CEIL_SCALE: float = 0.5

# Severity grade floor: minimum score by worst severity present
_SEVERITY_GRADE_FLOOR: dict[str, float] = {
    "critical": 0.0,
    "major": 3.0,
    "minor": 5.0,
}

# Legacy dampening constants
_MAX_PENALTY_MULTIPLIER: float = 1.30
_RATIO_DAMPENING_TABLE: list[tuple[float, float]] = [
    (3.0, 0.85),
    (2.0, 0.90),
    (1.0, 0.95),
    (0.5, 1.00),
    (0.0, 1.15),
    (-1.0, _MAX_PENALTY_MULTIPLIER),
]

# Canonical ordering from worst to best
GRADE_LADDER: list[str] = [
    "Insufficient",
    "Developing",
    "Proficient",
    "Exemplary",
]

_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (9, "Exemplary"),
    (7, "Good"),
    (5, "Adequate"),
    (3, "Poor"),
]

# ---------------------------------------------------------------------------
# Project-size scaling
# ---------------------------------------------------------------------------
_SCALE_TIERS: list[tuple[int, int]] = [
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
_WEIGHT_TRIPLE: str = "x3"
_WEIGHT_DOUBLE: str = "x2"


def scale_multiplier(source_file_count: int) -> int:
    """Return the size-based scaling multiplier for a project."""
    for threshold, multiplier in _SCALE_TIERS:
        if source_file_count >= threshold:
            return multiplier
    return 1


# Very small projects (e.g. demo / test repos) hit the violation type-cap
# thresholds (3 critical / 5 major) too aggressively: a handful of distinct
# critical types in a 10–30 file repo immediately drops the grade to Poor in
# graded mode, even though the same density on a "Medium" project would only
# drop it by one level. Mirror the large-project scaling at the small end.
_SMALL_PROJECT_FLOOR = 30
_SMALL_PROJECT_LENIENCY = 2


def small_project_multiplier(source_file_count: int) -> int:
    """Extra cap leniency for very small projects.

    Returns an additional multiplier on top of :func:`scale_multiplier`
    so the violation type caps and graded-mode drop thresholds scale up
    for tiny repos (where a few distinct types is noisier signal).
    """
    if 0 < source_file_count < _SMALL_PROJECT_FLOOR:
        return _SMALL_PROJECT_LENIENCY
    return 1


def effective_cap_multiplier(source_file_count: int) -> int:
    """Combined size-based multiplier used for violation type caps.

    Composes :func:`scale_multiplier` (raises caps for large projects)
    with :func:`small_project_multiplier` (raises caps for very small
    projects). The reported tier (``ScaleInfo.tier``) continues to use
    :func:`scale_multiplier` alone — leniency is invisible to the
    surface UI and only affects how harshly type counts are scored.
    """
    return scale_multiplier(source_file_count) * small_project_multiplier(source_file_count)
