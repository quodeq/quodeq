"""Contract: per-finding ``confidence`` is a UI/triage signal, never a grade input (#640).

``confidence`` (0-100) is set by the ``FindingEnricher`` downweights (non-prod path
-> 50, project-shape mismatch -> 40, prior-dismissal precedent -> 25) and powers the
dashboard's collapsible "Low confidence" grouping. It deliberately does NOT affect
the grade: the score reflects the code objectively, not heuristic false-positive
judgement or which findings a user has dismissed (letting dismissals raise a grade
would be gameable and would conflate "this was a false positive" with "I don't care
about this"). These tests pin that invariance so it cannot change silently.

If false-positive-aware grading is ever wanted, it should be designed on the
detection/severity side (cf. the deterministic provenance gate, #639), not bolted on
by weighting the grade with ``confidence``.
"""
from __future__ import annotations

from quodeq.analysis._report_constants import _COMPLIANCE_FIELDS, _VIOLATION_FIELDS
from quodeq.core.scoring._principle import compute_tallies
from quodeq.core.types.finding import Finding
from quodeq.services.scoring.projector_scoring import compute_principle_grade


def test_confidence_absent_from_scored_fields():
    """Structural guard: confidence is not among the fields scoring reads."""
    assert "confidence" not in _VIOLATION_FIELDS
    assert "confidence" not in _COMPLIANCE_FIELDS


def _v(severity: str, reason: str, confidence: int) -> dict:
    return {"severity": severity, "reason": reason, "confidence": confidence}


def test_tally_is_invariant_to_confidence():
    """The per-severity tally that feeds scoring ignores confidence entirely."""
    high = [_v("critical", "a", 100), _v("major", "b", 100), _v("minor", "c", 100)]
    low = [_v("critical", "a", 25), _v("major", "b", 40), _v("minor", "c", 50)]
    assert compute_tallies(high, []) == compute_tallies(low, [])


def _f(severity: str, reason: str, confidence: int) -> Finding:
    return Finding(
        practice_id="Modularity", verdict="violation", file="a.py", line=1,
        end_line=1, title="t", reason=reason, snippet="s", severity=severity,
        cwe=None, req="R1", req_refs=[], context="", dimension="maintainability",
        violation_type=None, scope="", confidence=confidence,
    )


def test_principle_grade_is_invariant_to_confidence():
    """The end-to-end principle grade must be identical regardless of confidence."""
    spec = [
        ("critical", "critical defect"),
        ("major", "major defect one"),
        ("major", "major defect two"),
        ("minor", "minor defect"),
    ]
    full_conf = [_f(sev, reason, 100) for sev, reason in spec]
    low_conf = [_f(sev, reason, 25) for sev, reason in spec]

    graded_full = compute_principle_grade(
        principle_id="Modularity", findings=full_conf, compliance=[],
    )
    graded_low = compute_principle_grade(
        principle_id="Modularity", findings=low_conf, compliance=[],
    )

    assert graded_full["score"] == graded_low["score"]
    assert graded_full["grade"] == graded_low["grade"]
    assert graded_full["finding_count"] == graded_low["finding_count"] == len(spec)
