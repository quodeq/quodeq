"""Principle-level scoring logic (internal module)."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.types import PrincipleScore
from quodeq.core.evidence.model import DEFAULT_WEIGHT
from quodeq.core.scoring.overall import MODE_NUMERICAL
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.scoring.internals import (
    build_deductions,
    compliance_dampening,
    compliance_lift,
    confidence_interval_for,
    count_grade_drops,
    drop_grade,
    evidence_has_taxonomy,
    score_to_grade_label,
    severity_grade_floor,
    tally_compliance_types_by_reason,
    tally_compliance_types_by_taxonomy,
    tally_types_by_reason,
    tally_types_by_taxonomy,
    violation_base,
    violation_ceiling,
)

_BASE_SCORE = 10


@dataclass(frozen=True)
class _PrincipleContext:
    """Scoring context for a single principle."""
    key: str
    pdata: dict
    pct: float
    vt_counts: dict[str, int]
    ct_counts: dict[str, int]
    dampening: float
    using_taxonomy: bool
    conf_level: str
    ci: dict
    scale_mult: int


def compute_tallies(
    violations: list, compliance: list,
) -> tuple[dict[str, int], dict[str, int], bool]:
    """Tally violation and compliance type counts, selecting taxonomy or reason mode."""
    using_taxonomy = evidence_has_taxonomy(violations)
    vt_counts = tally_types_by_taxonomy(violations) if using_taxonomy else tally_types_by_reason(violations)
    ct_counts = tally_compliance_types_by_taxonomy(compliance) if using_taxonomy else tally_compliance_types_by_reason(compliance)
    return vt_counts, ct_counts, using_taxonomy


def _base_kwargs(ctx: _PrincipleContext) -> dict:
    """Common keyword arguments shared by both scoring modes."""
    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }


def _score_numerical(
    ctx: _PrincipleContext, params: ScoringParams = DEFAULT_PARAMS,
) -> PrincipleScore:
    """Score a single principle in numerical mode."""
    kwargs = _base_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs, base_score=0,
            deductions=build_deductions({}, scale_multiplier=ctx.scale_mult),
            final_score=0.0, grade="Insufficient",
        )
    base = violation_base(ctx.vt_counts, params=params)
    lift = compliance_lift(ctx.ct_counts, ctx.vt_counts, params=params)
    raw = base + (_BASE_SCORE - base) * lift
    final_pts = round(max(severity_grade_floor(ctx.vt_counts, params=params),
                          min(violation_ceiling(ctx.vt_counts, params=params), raw)), 1)
    return PrincipleScore(
        **kwargs, base_score=round(base, 1),
        deductions=build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult),
        dampening_multiplier=lift, final_score=final_pts,
        grade=score_to_grade_label(final_pts, params=params),
    )


def _score_graded(
    ctx: _PrincipleContext, params: ScoringParams = DEFAULT_PARAMS,  # noqa: ARG001
) -> PrincipleScore:
    """Score a single principle in non-numerical (graded) mode.

    Accepts params only for scorer-signature symmetry with
    ``_score_numerical``; the legacy graded ladder is not user-tunable.
    """
    kwargs = _base_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs, base_grade="Insufficient", severity_drops=0,
            grade="Insufficient",
        )
    drops = count_grade_drops(ctx.vt_counts, scale_multiplier=ctx.scale_mult)
    return PrincipleScore(
        **kwargs, base_grade="Exemplary", severity_drops=drops,
        dampening_multiplier=ctx.dampening,
        grade=drop_grade("Exemplary", int(drops * ctx.dampening)),
    )


def _build_context(
    key: str, pdata: dict, scale_mult: int, files_read: int,
) -> _PrincipleContext:
    """Build scoring context for a single principle from its evidence data."""
    metrics = pdata.get("metrics", {})
    pct = metrics.get("compliance_percentage", 0.0)
    conf_level = metrics.get("confidence_level", "medium")
    vt_counts, ct_counts, using_taxonomy = compute_tallies(
        pdata.get("violations", []), pdata.get("compliance", []),
    )
    ci = confidence_interval_for(
        confidence_level=conf_level,
        is_balanced=metrics.get("is_balanced", True),
        total_instances=metrics.get("total_instances", 0),
        files_read=files_read,
    )
    return _PrincipleContext(
        key=key, pdata=pdata, pct=pct, vt_counts=vt_counts,
        ct_counts=ct_counts, dampening=compliance_dampening(ct_counts, vt_counts),
        using_taxonomy=using_taxonomy, conf_level=conf_level, ci=ci,
        scale_mult=scale_mult,
    )


def _score_all_principles(
    raw_principles: dict, mode: str, scale_mult: int, files_read: int,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, PrincipleScore]:
    """Score every principle and return the per-principle dict."""
    scorer = _score_numerical if mode == MODE_NUMERICAL else _score_graded
    return {
        key: scorer(_build_context(key, pdata, scale_mult, files_read), params)
        for key, pdata in raw_principles.items()
    }
