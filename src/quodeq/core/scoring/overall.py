"""Weighted overall score aggregation helpers for the scoring engine."""
from __future__ import annotations

from dataclasses import replace

from quodeq.core.types import OverallScore, PrincipleScore
from quodeq.core.types.scoring import ConfidenceLevel
from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.scoring.internals import (
    GRADE_LADDER,
    score_to_grade_label,
    weight_as_multiplier,
)

_GRADE_INDEX: dict[str, int] = {g: i for i, g in enumerate(GRADE_LADDER)}

MODE_NUMERICAL = "numerical"
_LOW_CONFIDENCE_REASON = (
    "Thin evidence: {pct}% of this dimension's observations come from principles with few findings"
)
_LOW_CONFIDENCE_SHARE = 0.5


def accumulate_weights(
    principles_scores: dict[str, PrincipleScore], mode: str,
) -> tuple[float, float, int, float]:
    """Sum weighted values. Returns (total_weight, total_value, total_count, low_confidence_weight).

    Numerical mode weighs a principle by its observation times the configured
    multiplier; when no principle carries observation (legacy inputs) every
    principle weighs its multiplier alone. Graded mode weighs by multiplier.
    """
    scorable = [
        p for p in principles_scores.values()
        if p.grade != Grade.INSUFFICIENT and (mode != MODE_NUMERICAL or p.final_score is not None)
    ]
    use_observation = mode == MODE_NUMERICAL and any(p.observation > 0 for p in scorable)
    total_weight = 0.0
    total_value = 0.0
    low_weight = 0.0
    for pdata in scorable:
        weight = float(weight_as_multiplier(pdata.weight))
        if use_observation:
            weight *= pdata.observation
        total_weight += weight
        if pdata.confidence_level == ConfidenceLevel.LOW:
            low_weight += weight
        if mode == MODE_NUMERICAL:
            total_value += (pdata.final_score or 0.0) * weight
        else:
            total_value += _GRADE_INDEX[pdata.grade] * weight
    return total_weight, total_value, len(principles_scores), low_weight


def build_overall_result(
    mode: str, total_weight: float, total_value: float,
    params: ScoringParams = DEFAULT_PARAMS,
) -> OverallScore:
    """Build the overall result from aggregated weights."""
    if mode == MODE_NUMERICAL:
        mean_score = round(total_value / total_weight, 1)
        return OverallScore(
            weighted_score=mean_score,
            grade=score_to_grade_label(mean_score, params=params),
            total_weight=total_weight,
        )
    mean_index = total_value / total_weight
    ladder_pos = min(len(GRADE_LADDER) - 1, round(mean_index))
    return OverallScore(weighted_grade=GRADE_LADDER[ladder_pos], total_weight=total_weight)


def weighted_overall(
    principles_scores: dict[str, PrincipleScore], mode: str,
    params: ScoringParams = DEFAULT_PARAMS,
) -> OverallScore:
    """Compute a weighted overall score or grade from per-principle results."""
    tw, tv, total, low = accumulate_weights(principles_scores, mode)

    if tw == 0:
        if mode == MODE_NUMERICAL:
            return OverallScore(weighted_score=0.0, grade=Grade.INSUFFICIENT)
        return OverallScore(weighted_grade=Grade.INSUFFICIENT)

    result = build_overall_result(mode, tw, tv, params)

    if total > 0 and low > tw * _LOW_CONFIDENCE_SHARE:
        pct = round(100 * low / tw)
        result = replace(
            result, confidence="low",
            confidence_reason=_LOW_CONFIDENCE_REASON.format(pct=pct),
        )
    return result
