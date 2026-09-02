"""Parity tests: projector_scoring vs legacy rescore_dimensions.

Split from test_projector_scoring.py. The parity tests compare
projector_scoring output to legacy rescore_dimensions for known inputs.
Both call the same scoring internals, so parity is structural -- the tests
guard against drift.

Both engines now apply the same confidence-level check (see
``core.evidence.model.classify_confidence_level``) so they agree on which
principles qualify for scoring vs Insufficient. Inputs below carry enough
findings to clear the medium-confidence threshold (5 by default at
source_file_count=0), so both engines score the principles instead of
bailing out to Insufficient.

Shared `_f` finding builder lives in tests/core/_projector_scoring_fixtures.py.
"""
from __future__ import annotations

from quodeq.core.scoring.projector_scoring import compute_dimension_score, compute_principle_grade

from tests.core._projector_scoring_fixtures import _f


def _legacy_dim_score(violations, compliance) -> float | None:
    """Compute a dimension score via the underlying legacy scoring path.

    Calls _score_principle per principle and weighted_overall to aggregate,
    mirroring exactly what _rescore_dimension does after filtering dismissed
    findings.
    """
    from quodeq.core.scoring.overall import MODE_NUMERICAL, weighted_overall
    from quodeq.services.rescore import _group_by_principle, _score_all_principles

    pv = _group_by_principle(violations)
    pc = _group_by_principle(compliance)
    principle_scores, _ = _score_all_principles(pv, pc)
    overall = weighted_overall(principle_scores, MODE_NUMERICAL)
    return overall.weighted_score


def _new_dim_score(violations, compliance) -> float | None:
    """Compute the same dimension score via projector_scoring."""
    violations_by: dict = {}
    for v in violations:
        violations_by.setdefault(v.practice_id, []).append(v)
    comp_by: dict = {}
    for c in compliance:
        comp_by.setdefault(c.practice_id, []).append(c)
    p_grades = [
        compute_principle_grade(
            principle_id=p,
            findings=violations_by.get(p, []),
            compliance=comp_by.get(p, []),
        )
        for p in sorted(set(violations_by) | set(comp_by))
    ]
    return compute_dimension_score(dimension="Security", principle_grades=p_grades)["score"]


def test_parity_single_principle_sufficient_violations() -> None:
    """5 same-severity violations clears the medium-confidence floor."""
    violations = [_f(f"R{i}", "P1", "high") for i in range(5)]
    compliance = []
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_single_principle_violation_and_compliance() -> None:
    violations = [_f(f"V{i}", "P1", "high") for i in range(3)]
    compliance = [_f(f"C{i}", "P1", "low", verdict="compliance") for i in range(2)]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_multiple_principles() -> None:
    """Each principle has enough findings to clear the confidence floor."""
    violations = [_f(f"V{i}", "P1", "high") for i in range(3)] \
        + [_f(f"W{i}", "P2", "critical") for i in range(3)]
    compliance = [_f(f"C{i}", "P1", "low", verdict="compliance") for i in range(2)] \
        + [_f(f"D{i}", "P2", "low", verdict="compliance") for i in range(2)]
    legacy = _legacy_dim_score(violations, compliance)
    new = _new_dim_score(violations, compliance)
    assert new == legacy, f"Parity broken: legacy={legacy}, new={new}"


def test_parity_low_confidence_returns_insufficient_in_both() -> None:
    """Thin evidence (1 finding) must yield Insufficient in both engines.

    This is the contract that closed the dashboard-vs-CLI score split.
    Score may be ``None`` (projector) or ``0.0`` (legacy weighted_overall
    fallback), but the *grade* must be Insufficient.
    """
    from quodeq.core.scoring.overall import MODE_NUMERICAL, weighted_overall
    from quodeq.services.rescore import _group_by_principle, _score_all_principles

    violations = [_f("R1", "P1", "high")]
    compliance = []

    # Legacy
    pv = _group_by_principle(violations)
    pc = _group_by_principle(compliance)
    legacy_principle_scores, _ = _score_all_principles(pv, pc)
    legacy_overall = weighted_overall(legacy_principle_scores, MODE_NUMERICAL)
    assert legacy_overall.grade == "Insufficient"

    # New
    p_grade = compute_principle_grade(principle_id="P1", findings=violations, compliance=[])
    assert p_grade["grade"] == "Insufficient"
    new_dim = compute_dimension_score(dimension="Security", principle_grades=[p_grade])
    assert new_dim["grade"] == "Insufficient"
