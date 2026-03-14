"""Numerical-mode scoring helpers: deduction computation and grade drops."""
from __future__ import annotations

import os

# Progressive drop tables: (min_type_count_inclusive, levels_to_drop).
# Checked top-to-bottom; first matching row wins.
_CRITICAL_DROP_TABLE: list[tuple[int, int]] = [(12, 3), (4, 2), (1, 1)]
_MAJOR_DROP_TABLE: list[tuple[int, int]] = [(36, 3), (12, 2), (4, 1)]

# Per-type deduction constants for numerical mode.
_CRITICAL_PENALTY = float(os.environ.get("QUODEQ_CRITICAL_PENALTY", "2.0"))
_MAJOR_PENALTY = float(os.environ.get("QUODEQ_MAJOR_PENALTY", "1.0"))
_MINOR_PENALTY = float(os.environ.get("QUODEQ_MINOR_PENALTY", "0.25"))

_CRITICAL_SCORE_CAP = 3
_MAJOR_SCORE_CAP = 5
_MAX_SCORE = 10


def build_deductions(violation_type_counts: dict[str, int], scale_multiplier: int = 1) -> dict:
    """Compute point deductions for numerical mode.

    Rules:
    - Each distinct critical violation type removes 2.0 points; types are capped
      at 3*scale before computing the deduction.
    - Each distinct major violation type removes 1.0 point; capped at 5*scale.
    - Minor violation types are NOT capped — every distinct type deducts 0.25.
    - If the raw critical count reaches 3*scale, the score is hard-capped at 3.
    - If the raw major count reaches 5*scale, the score is hard-capped at 5.
    - Both caps may apply simultaneously (take min).
    """
    n_critical = violation_type_counts.get("critical", 0)
    n_major = violation_type_counts.get("major", 0)
    n_minor = violation_type_counts.get("minor", 0)

    critical_type_cap = _CRITICAL_SCORE_CAP * scale_multiplier
    major_type_cap = _MAJOR_SCORE_CAP * scale_multiplier

    effective_critical = min(n_critical, critical_type_cap)
    effective_major = min(n_major, major_type_cap)

    critical_deduction = effective_critical * _CRITICAL_PENALTY
    major_deduction = effective_major * _MAJOR_PENALTY
    minor_deduction = n_minor * _MINOR_PENALTY

    cap_from_critical = _CRITICAL_SCORE_CAP if n_critical >= critical_type_cap else _MAX_SCORE
    cap_from_major = _MAJOR_SCORE_CAP if n_major >= major_type_cap else _MAX_SCORE

    return {
        "critical_type_count": n_critical,
        "major_type_count": n_major,
        "minor_type_count": n_minor,
        "critical_deduction": critical_deduction,
        "major_deduction": major_deduction,
        "minor_deduction": minor_deduction,
        "total_deduction": critical_deduction + major_deduction + minor_deduction,
        "critical_cap": cap_from_critical,
        "major_cap": cap_from_major,
    }


def count_grade_drops(violation_type_counts: dict[str, int], scale_multiplier: int = 1) -> int:
    """Return the number of grade levels to drop in non-numerical mode.

    Drop table thresholds are multiplied by scale_multiplier so that large
    projects require proportionally more violation types before incurring drops.
    """
    n_critical = violation_type_counts.get("critical", 0)
    n_major = violation_type_counts.get("major", 0)

    critical_drops = 0
    for min_count, levels in _CRITICAL_DROP_TABLE:
        if n_critical >= min_count * scale_multiplier:
            critical_drops = levels
            break

    major_drops = 0
    for min_count, levels in _MAJOR_DROP_TABLE:
        if n_major >= min_count * scale_multiplier:
            major_drops = levels
            break

    return max(critical_drops, major_drops)
