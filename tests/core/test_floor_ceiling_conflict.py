"""The severity floor must not override the volume ceiling.

`severity_grade_floor` says "only minor issues, so you can't be that bad".
`violation_ceiling` says "this much violation load caps you". They are both
guards, and they cross when a principle has a LOT of issues that happen to all
be minor. The clamp resolved that by letting the floor win unconditionally:

    final = max(floor, min(ceil, raw))

so `usability Learnability` on the quodeq project -- 250 distinct minor
violation types, 0 major, 0 critical -- came out at floor=8.0 ("Good") while
the ceiling said 7.01 and the curve said 3.35. The one guard that encodes
VOLUME was the one discarded, which is precisely what made 269 findings
invisible to the grade.

Clamping to the floor first and the ceiling last keeps the ceiling
authoritative. Note the two orderings are algebraically identical whenever
floor <= ceil, which is every other principle on that project (34 of 35), so
this only ever moves the contradictory case.
"""
from __future__ import annotations

import pytest

from quodeq.core.scoring.internals import (
    severity_grade_floor,
    violation_base,
    violation_ceiling,
    compliance_lift,
)
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.core.scoring.projector_scoring import compute_principle_grade
from quodeq.core.types.finding import Finding


def _clamp(floor: float, ceil: float, raw: float) -> float:
    """The production clamp, imported by value from both call sites."""
    return min(ceil, max(floor, raw))


@pytest.mark.parametrize(
    ("floor", "ceil", "raw"),
    [
        (0.0, 10.0, 5.0),    # wide open
        (5.0, 7.0, 6.0),     # raw between
        (5.0, 7.0, 2.0),     # raw below floor
        (5.0, 7.0, 9.0),     # raw above ceiling
        (8.0, 8.0, 3.0),     # floor == ceil
        (0.0, 6.5, 6.5),     # raw at ceiling
    ],
)
def test_agrees_with_the_old_ordering_whenever_floor_fits_under_the_ceiling(
    floor: float, ceil: float, raw: float,
) -> None:
    """The change must be surgical: identical everywhere the guards don't cross."""
    assert floor <= ceil
    assert _clamp(floor, ceil, raw) == max(floor, min(ceil, raw))


def test_ceiling_wins_when_the_guards_cross() -> None:
    """Learnability's real numbers: 250 minor types, no major, no critical."""
    floor, ceil, raw = 8.0, 7.01, 3.35
    assert floor > ceil, "this is the contradictory case"
    assert _clamp(floor, ceil, raw) == 7.01
    # The old ordering handed back the floor and threw the ceiling away.
    assert max(floor, min(ceil, raw)) == 8.0


def _minor(i: int, verdict: str = "violation") -> Finding:
    """Distinct `reason` per item so tally_types counts them as separate types."""
    return Finding(
        practice_id="Learnability", verdict=verdict, file=f"f{i}.py", line=i,
        end_line=i, title="t", reason=f"distinct reason {i}", snippet="s",
        severity="minor", cwe=None, req=f"U-LRN-{i}", req_refs=[], context="",
        dimension="usability", violation_type=None, scope="", confidence=100,
    )


def test_principle_grade_does_not_read_good_under_a_pile_of_minor_findings() -> None:
    """The production path, not a hand-rolled clamp.

    250 minor violations against 53 compliances puts the minor-only floor (8.0)
    above the volume ceiling (~7.0). The grade must respect the ceiling.
    """
    result = compute_principle_grade(
        principle_id="Learnability",
        findings=[_minor(i) for i in range(250)],
        compliance=[_minor(i, verdict="compliance") for i in range(53)],
        source_file_count=1800,
        scale_multiplier=1,
    )
    assert result["score"] is not None
    assert result["score"] < 8.0, (
        f"269 findings scored {result['score']} -- the severity floor "
        "overrode the volume ceiling and hid the backlog"
    )


def test_the_evidence_path_agrees_with_the_projector() -> None:
    """The clamp exists in THREE places and real runs use this one.

    `rescore_dimensions` only falls back to services/rescore's copy when a run
    has no evidence on disk; every modern run goes through
    services/evidence_rescore -> core/scoring/engine -> _principle. Fixing the
    other two copies left the displayed grade completely unchanged, and the
    projector-level test above still passed -- which is exactly how a
    three-copy invariant rots. Pin the path users actually hit.
    """
    from quodeq.core.scoring._principle import _score_numerical, _build_context

    pdata = {
        "violations": [{"severity": "minor", "reason": f"distinct {i}"} for i in range(250)],
        "compliance": [{"severity": "minor", "reason": f"ok {i}"} for i in range(53)],
        "metrics": {"compliance_percentage": 17.5, "confidence_level": "high",
                    "is_balanced": True, "total_instances": 303},
    }
    ctx = _build_context("Learnability", pdata, scale_mult=1, files_read=1800)
    score = _score_numerical(ctx, params=DEFAULT_PARAMS)
    assert score.final_score < 8.0, (
        f"evidence path scored {score.final_score}: the severity floor still "
        "overrides the volume ceiling where it actually matters"
    )


def test_a_pile_of_minor_findings_cannot_read_as_good() -> None:
    """End to end through the real primitives, no hand-picked numbers."""
    violations = {"critical": 0, "major": 0, "minor": 250}
    compliance = {"minor": 53}
    floor = severity_grade_floor(violations, params=DEFAULT_PARAMS)
    ceil = violation_ceiling(violations, params=DEFAULT_PARAMS)
    base = violation_base(violations, params=DEFAULT_PARAMS)
    lift = compliance_lift(compliance, violations, params=DEFAULT_PARAMS)
    raw = base + (10.0 - base) * lift

    assert floor == 8.0 and ceil < floor, "minor-only floor sits above the volume ceiling"
    assert round(_clamp(floor, ceil, raw), 1) < 8.0
