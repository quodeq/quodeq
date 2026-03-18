"""Confidence interval estimation for scoring results."""
from __future__ import annotations

_CI_BASE_WIDTH = 1.0
_CI_LOW_CONFIDENCE_PENALTY = 1.0
_CI_MEDIUM_CONFIDENCE_PENALTY = 0.5
_CI_UNBALANCED_PENALTY = 0.5
_CI_SPARSITY_PENALTY = 0.5
_SPARSITY_RATIO = 0.01
_CI_UNSTABLE_THRESHOLD = 1.5
_GRADE_UNSTABLE_LABEL = "+/- 1 level"
_GRADE_STABLE_LABEL = "stable"


def confidence_interval_for(
    confidence_level: str,
    is_balanced: bool,
    total_instances: int,
    files_read: int = 0,
) -> dict:
    """Estimate the uncertainty width for a principle score.

    Starting width is 1.0. Additional half-points are added when:
    - confidence_level is 'low' (+1.0) or 'medium' (+0.5)
    - the sample is unbalanced (+0.5)
    - the instance count is sparse relative to files actually read (+0.5)

    grade_stability is 'stable' unless the interval exceeds 1.5.
    """
    width = _CI_BASE_WIDTH

    if confidence_level == "low":
        width += _CI_LOW_CONFIDENCE_PENALTY
    elif confidence_level == "medium":
        width += _CI_MEDIUM_CONFIDENCE_PENALTY

    if not is_balanced:
        width += _CI_UNBALANCED_PENALTY

    sparsity_floor = _SPARSITY_RATIO * files_read if files_read > 0 else 0
    if sparsity_floor > 0 and total_instances < sparsity_floor:
        width += _CI_SPARSITY_PENALTY

    return {
        "confidence_interval": width,
        "grade_stability": _GRADE_UNSTABLE_LABEL if width > _CI_UNSTABLE_THRESHOLD else _GRADE_STABLE_LABEL,
    }
