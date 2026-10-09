"""Compliance dampening and graded-mode scoring tests (split from test_scoring)."""
from __future__ import annotations

from quodeq.core.evidence.model import Evidence, PrincipleEvidence
from quodeq.core.scoring.engine import score_evidence

from tests._evidence_helpers import make_evidence_with_confidence

_TEST_FILE = "a.ts"
_TEST_SNIPPET = "eval(x)"


# ---------------------------------------------------------------------------
# Compliance dampening tests
# ---------------------------------------------------------------------------

def test_balanced_ratio_lifts_score():
    """1 critical violation + 1 critical compliance: compliance lifts the base.

    Violation mass 8.0, compliance mass 2.0.
    """
    violations = [
        {"file": _TEST_FILE, "line": 1, "snippet": _TEST_SNIPPET, "reason": "r",
         "severity": "critical", "vt": "code-injection"},
    ]
    compliance = [
        {"file": "c0.ts", "line": 1, "snippet": "ok", "reason": "r0",
         "severity": "critical", "vt": "safe-eval"},
    ]
    ev = make_evidence_with_confidence(
        confidence_level="high",
        violations=violations,
        compliance=compliance,
        n_violations=1,
        n_compliance=1,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.final_score == 6.2


def test_strong_compliance_lifts_toward_ceiling():
    """1 major violation + 3 major compliance types: strong lift.

    Violation mass 4.0 against compliance mass 6.0 lifts the base toward the ceiling.
    """
    violations = [
        {"file": _TEST_FILE, "line": 1, "snippet": "x", "reason": "r",
         "severity": "major", "vt": "bad-pattern"},
    ]
    compliance = [
        {"file": f"c{i}.ts", "line": i, "snippet": "ok", "reason": f"r{i}",
         "severity": "major", "vt": f"safe-{i}"}
        for i in range(3)
    ]
    ev = make_evidence_with_confidence(
        confidence_level="high",
        violations=violations,
        compliance=compliance,
        n_violations=1,
        n_compliance=3,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.final_score == 8.4


def test_no_compliance_gives_base_only():
    """No compliance → score equals the violation base, no lift."""
    violations = [
        {"file": _TEST_FILE, "line": 1, "snippet": "x", "reason": "r",
         "severity": "major", "vt": "bad"},
    ]
    ev = make_evidence_with_confidence(
        confidence_level="high",
        violations=violations,
        compliance=[],
        n_violations=1,
        n_compliance=0,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.dampening_multiplier == 0.0  # lift = 0 (no compliance)
    assert ts001.final_score == 7.6


def test_weak_compliance_small_lift():
    """4 minor violations + 1 minor compliance: small lift above base."""
    violations = [
        {"file": f"v{i}.ts", "line": i, "snippet": "x", "reason": f"r{i}",
         "severity": "minor", "vt": f"vt-{i}"}
        for i in range(4)
    ]
    compliance = [
        {"file": "c.ts", "line": 1, "snippet": "ok", "reason": "r",
         "severity": "minor", "vt": "comp-1"},
    ]
    ev = make_evidence_with_confidence(
        confidence_level="high",
        violations=violations,
        compliance=compliance,
        n_violations=4,
        n_compliance=1,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.final_score == 8.9


def test_dampening_in_graded_mode():
    """Dampening should reduce grade drops in non-numerical mode too.

    4 critical violations (weight 4×8=32) need >= 32 weighted compliance
    for ratio 1.0 → 0.95x. 4 critical compliance types (4×8=32) provide exactly that.
    """
    violations = [
        {"file": f"v{i}.ts", "line": i, "snippet": "x", "reason": f"r{i}",
         "severity": "critical", "vt": f"vt-{i}"}
        for i in range(4)
    ]
    compliance = [
        {"file": f"c{i}.ts", "line": i, "snippet": "ok", "reason": f"r{i}",
         "severity": "critical", "vt": f"comp-{i}"}
        for i in range(4)
    ]
    ev = make_evidence_with_confidence(
        confidence_level="high",
        violations=violations,
        compliance=compliance,
        n_violations=4,
        n_compliance=4,
    )
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores.principles["ts-001"]
    assert ts001.dampening_multiplier == 0.95
    assert ts001.severity_drops == 2
    assert ts001.grade == "Proficient"


def test_overall_low_confidence_when_most_observation_is_thin():
    """Overall is flagged low confidence when most observation comes from thin principles."""
    def _thin(pid):
        return PrincipleEvidence(
            practice_id=pid, display_name=pid.upper(), dimension="security",
            severity="high", violations=[], compliance=[
                {"file": _TEST_FILE, "line": 1, "snippet": "ok", "reason": "safe"},
            ],
            metrics={"total_instances": 1, "compliant": 1, "violating": 0,
                     "compliance_percentage": 100.0, "confidence_level": "low", "is_balanced": False},
        )

    pe_high = PrincipleEvidence(
        practice_id="p3", display_name="P3", dimension="security",
        severity="high", violations=[], compliance=[
            {"file": _TEST_FILE, "line": 1, "snippet": "ok", "reason": "safe"},
        ],
        metrics={"total_instances": 10, "compliant": 10, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "high", "is_balanced": False},
    )
    ev = Evidence(
        repository="test", language="ts", date="2026-03-03",
        source_file_count=100, files_read=50, coverage_pct=50.0,
        principles={"p1": _thin("p1"), "p2": _thin("p2"), "p3": pe_high},
    )
    scores = score_evidence(ev, mode="numerical")
    assert scores.overall.confidence == "low"
    assert "Thin evidence" in scores.overall.confidence_reason
