"""Principle-level scoring logic (internal module)."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.types import PrincipleScore
from quodeq.core.evidence.model import DEFAULT_WEIGHT
from quodeq.core.scoring.overall import MODE_NUMERICAL
from quodeq.core.scoring.internals import (
    build_deductions,
    compliance_dampening,
    compliance_lift_from_wv,
    confidence_interval_for,
    count_grade_drops,
    density_weighted_sum,
    drop_grade,
    evidence_has_taxonomy,
    score_to_grade_label,
    severity_grade_floor,
    tally_compliance_types_by_reason,
    tally_compliance_types_by_taxonomy,
    tally_types_by_reason,
    tally_types_by_taxonomy,
    violation_base_from_wv,
    violation_ceiling_from_wv,
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
    # Density-aware weighted sums (severity weight × log2(1 + instances)
    # per (severity, type) group). Used by violation_base_from_wv and
    # violation_ceiling_from_wv so a principle with many instances of
    # one type is punished more than one with a single instance.
    wv_density: float
    wc_density: float
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


def _score_numerical(ctx: _PrincipleContext) -> PrincipleScore:
    """Score a single principle in numerical mode."""
    kwargs = _base_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs, base_score=0,
            deductions=build_deductions({}, scale_multiplier=ctx.scale_mult),
            final_score=0.0, grade="Insufficient",
        )
    base = violation_base_from_wv(ctx.wv_density)
    # compliance_lift uses an unweighted compliance count vs the weighted
    # violation total — keep that legacy semantic to avoid disturbing the
    # lift balance that's already calibrated. We only feed the
    # density-aware wv on the violation side.
    cc = sum(ctx.ct_counts.get(sev, 0) for sev in ctx.ct_counts)
    lift = compliance_lift_from_wv(cc, ctx.wv_density)
    raw = base + (_BASE_SCORE - base) * lift
    final_pts = round(max(severity_grade_floor(ctx.vt_counts),
                          min(violation_ceiling_from_wv(ctx.wv_density), raw)), 1)
    return PrincipleScore(
        **kwargs, base_score=round(base, 1),
        deductions=build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult),
        dampening_multiplier=lift, final_score=final_pts,
        grade=score_to_grade_label(final_pts),
    )


def _score_graded(ctx: _PrincipleContext) -> PrincipleScore:
    """Score a single principle in non-numerical (graded) mode."""
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
    violations = pdata.get("violations", [])
    compliance = pdata.get("compliance", [])
    vt_counts, ct_counts, using_taxonomy = compute_tallies(violations, compliance)
    wv_density = density_weighted_sum(violations, using_taxonomy=using_taxonomy)
    wc_density = density_weighted_sum(compliance, using_taxonomy=using_taxonomy)
    ci = confidence_interval_for(
        confidence_level=conf_level,
        is_balanced=metrics.get("is_balanced", True),
        total_instances=metrics.get("total_instances", 0),
        files_read=files_read,
    )
    return _PrincipleContext(
        key=key, pdata=pdata, pct=pct, vt_counts=vt_counts,
        ct_counts=ct_counts, wv_density=wv_density, wc_density=wc_density,
        dampening=compliance_dampening(ct_counts, vt_counts),
        using_taxonomy=using_taxonomy, conf_level=conf_level, ci=ci,
        scale_mult=scale_mult,
    )


def _score_all_principles(
    raw_principles: dict, mode: str, scale_mult: int, files_read: int,
) -> dict[str, PrincipleScore]:
    """Score every principle and return the per-principle dict."""
    scorer = _score_numerical if mode == MODE_NUMERICAL else _score_graded
    return {
        key: scorer(_build_context(key, pdata, scale_mult, files_read))
        for key, pdata in raw_principles.items()
    }
