"""Public scoring API — delegates principle-level work to _principle."""
from __future__ import annotations

from quodeq.core.types import ScaleInfo, ScoringResult
from quodeq.core.evidence.model import Evidence
from quodeq.core.scoring.overall import weighted_overall
from quodeq.core.scoring.internals import (
    SCALE_TIER_NAMES, effective_cap_multiplier, scale_multiplier, score_to_grade_label,
)
from quodeq.core.scoring._principle import _score_all_principles, compute_tallies


def grade_for_score(score: float) -> str:
    """Alias for score_to_grade_label — kept for public API compatibility."""
    return score_to_grade_label(score)


def confidence_label(level: str) -> str:
    """Return a human-readable confidence label."""
    return {"low": "Low", "medium": "Medium", "high": "High"}.get(level, level)


def run_scoring(evidence: dict, mode: str) -> ScoringResult:
    """Compute per-principle scores and return the full result."""
    source_file_count = evidence.get("source_file_count", 0)
    files_read = evidence.get("files_read", 0)
    # `scale_mult` is the surfaced tier (Small / Medium / …); `cap_mult`
    # is what the scoring math uses for violation type caps and graded
    # drop thresholds — equal for typical projects, but raised at the
    # very-small end so e.g. a 5-file demo isn't held to the same hard
    # caps as a 100-file mid-size project.
    scale_mult = scale_multiplier(source_file_count)
    cap_mult = effective_cap_multiplier(source_file_count)

    per_principle = _score_all_principles(
        evidence.get("principles", {}), mode, cap_mult, files_read,
    )
    return ScoringResult(
        repository=evidence.get("repository", ""),
        discipline=evidence.get("discipline", ""),
        date=evidence.get("date", ""),
        mode=mode,
        principles=per_principle,
        overall=weighted_overall(per_principle, mode),
        scale=ScaleInfo(
            tier=SCALE_TIER_NAMES.get(scale_mult, "Small"),
            multiplier=scale_mult,
            files_read=files_read,
        ),
    )


def score_evidence(evidence: Evidence, mode: str = "numerical") -> ScoringResult:
    """Score Evidence using the scoring engine."""
    return run_scoring(evidence.to_evidence_dict(), mode=mode)
