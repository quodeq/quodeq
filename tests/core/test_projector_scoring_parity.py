"""Parity tests: the projector's scoring vs the core engine.

Parity is core engine vs projector: the reference side runs the CLI's
``core.scoring.principle.score_all_principles`` over evidence-dict
principles built from the same findings, then ``weighted_overall``; the
projector side runs ``compute_principle_grade`` + ``compute_dimension_score``.
Both build requirement masses with the same primitives, so parity is
structural and these tests guard against drift. Thin evidence is scored (and
marked low confidence) by both rather than gated to Insufficient.

Shared `_f` finding builder lives in tests/core/_projector_scoring_fixtures.py.
"""
from __future__ import annotations

from quodeq.core.evidence.model import classify_confidence_level
from quodeq.core.scoring.internals import finding_to_scoring_dict
from quodeq.core.scoring.overall import MODE_NUMERICAL, weighted_overall
from quodeq.core.scoring.principle import score_all_principles
from quodeq.core.scoring.projector_scoring import (
    PrincipleGradeScale,
    compute_dimension_score,
    compute_principle_grade,
)

from tests.core._projector_scoring_fixtures import _f


def _evidence_principles(violations, compliance) -> dict:
    """Evidence-dict principles, the shape the CLI engine scores."""
    principles: dict = {}
    for key, rows in (("violations", violations), ("compliance", compliance)):
        for f in rows:
            principles.setdefault(f.practice_id, {"violations": [], "compliance": []})[key].append(
                finding_to_scoring_dict(f),
            )
    for pdata in principles.values():
        pdata["metrics"] = {"confidence_level": classify_confidence_level(
            len(pdata["violations"]), len(pdata["compliance"]),
        )}
    return principles


def _legacy_dim_score(violations, compliance) -> float | None:
    """The dimension score the core engine gives the same findings."""
    principle_scores = score_all_principles(
        _evidence_principles(violations, compliance), MODE_NUMERICAL, 1, 0, source_file_count=0,
    )
    return weighted_overall(principle_scores, MODE_NUMERICAL).weighted_score


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
            scale=PrincipleGradeScale(source_file_count=0),
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


def test_parity_thin_evidence_is_scored_in_both() -> None:
    """One finding is scored (not gated) and marked low confidence by both engines."""
    violations = [_f("R1", "P1", "critical")]
    legacy = _legacy_dim_score(violations, [])
    p_grade = compute_principle_grade(principle_id="P1", findings=violations, compliance=[])
    assert p_grade["grade"] != "Insufficient" and p_grade["confidence"] == "low"
    new_dim = compute_dimension_score(dimension="Security", principle_grades=[p_grade])
    assert new_dim["score"] == legacy
    assert new_dim["confidence"] == "low"


def test_dimension_score_weighs_by_observation_and_flags_thin_dimensions() -> None:
    heavy = {"principle_id": "a", "score": 4.6, "grade": "Poor", "observation": 400.0, "confidence": "high"}
    thin = {"principle_id": "b", "score": 10.0, "grade": "Exemplary", "observation": 1.3, "confidence": "low"}
    out = compute_dimension_score(dimension="Security", principle_grades=[heavy, thin])
    assert 4.6 <= out["score"] <= 4.7 and out["confidence"] is None
    thin_only = compute_dimension_score(dimension="Security", principle_grades=[thin, dict(thin, principle_id="c")])
    assert thin_only["confidence"] == "low"
