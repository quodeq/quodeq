"""Weighted overall score aggregation helpers for the scoring engine."""
from __future__ import annotations

from dataclasses import replace

from quodeq.core.types import OverallScore, PrincipleScore
from quodeq.core.scoring.internals import (
    GRADE_LADDER,
    score_to_grade_label,
    weight_as_multiplier,
)

_GRADE_INDEX: dict[str, int] = {g: i for i, g in enumerate(GRADE_LADDER)}

MODE_NUMERICAL = "numerical"
_INSUFFICIENT_MAJORITY_RATIO = 0.5


def accumulate_weights(
    principles_scores: dict[str, PrincipleScore], mode: str,
) -> tuple[int, float, int, int]:
    """Sum weighted values across scorable principles.

    Returns (total_weight, total_value, total_count, insufficient_count).
    """
    total_count = len(principles_scores)
    insufficient_count = sum(
        1 for p in principles_scores.values() if p.grade == "Insufficient"
    )
    total_weight = 0
    total_value = 0.0
    for pdata in principles_scores.values():
        if pdata.grade == "Insufficient":
            continue
        multiplier = weight_as_multiplier(pdata.weight)
        total_weight += multiplier
        if mode == MODE_NUMERICAL:
            total_value += (pdata.final_score or 0.0) * multiplier
        else:
            total_value += _GRADE_INDEX[pdata.grade] * multiplier
    return total_weight, total_value, total_count, insufficient_count


def build_overall_result(mode: str, total_weight: int, total_value: float) -> OverallScore:
    """Build the overall result from aggregated weights."""
    if mode == MODE_NUMERICAL:
        mean_score = round(total_value / total_weight, 1)
        return OverallScore(
            weighted_score=mean_score,
            grade=score_to_grade_label(mean_score),
            total_weight=total_weight,
        )
    mean_index = total_value / total_weight
    ladder_pos = min(len(GRADE_LADDER) - 1, round(mean_index))
    return OverallScore(weighted_grade=GRADE_LADDER[ladder_pos], total_weight=total_weight)


def weighted_overall(principles_scores: dict[str, PrincipleScore], mode: str) -> OverallScore:
    """Compute a weighted overall score or grade from per-principle results."""
    tw, tv, total, insuff = accumulate_weights(principles_scores, mode)

    if tw == 0:
        if mode == MODE_NUMERICAL:
            return OverallScore(weighted_score=0.0, grade="Insufficient")
        return OverallScore(weighted_grade="Insufficient")

    result = build_overall_result(mode, tw, tv)

    if total > 0 and insuff > total * _INSUFFICIENT_MAJORITY_RATIO:
        scored = total - insuff
        result = replace(
            result,
            confidence="low",
            confidence_reason=f"Only {scored}/{total} principles had sufficient evidence",
        )
    return result
