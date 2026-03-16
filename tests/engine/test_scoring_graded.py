"""Compliance dampening and graded-mode scoring tests (split from test_scoring)."""
from __future__ import annotations

from quodeq.engine.evidence import Evidence, PrincipleEvidence
from quodeq.engine.scoring import score_evidence

from tests.engine.conftest import make_evidence_with_confidence


# ---------------------------------------------------------------------------
# Compliance dampening tests
# ---------------------------------------------------------------------------

def test_balanced_ratio_dampens_deductions():
    """Severity-weighted compliance/violation ratio >= 1.0 -> 0.95 dampening.

    1 critical violation (weight 8) needs >= 8 weighted compliance to reach 1.0.
    1 critical compliance (weight 8) provides exactly that.
    """
    violations = [
        {"file": "a.ts", "line": 1, "snippet": "eval(x)", "reason": "r",
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
    assert ts001.dampening_multiplier == 0.95
    assert ts001.final_score == 8.1


def test_strong_compliance_ratio_gives_max_discount():
    """Severity-weighted ratio >= 3.0 -> 0.85 dampening (max discount).

    1 major violation (weight 4) needs >= 12 weighted compliance for 3.0 ratio.
    3 major compliance types (weight 3×4=12) provide exactly that.
    """
    violations = [
        {"file": "a.ts", "line": 1, "snippet": "x", "reason": "r",
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
    assert ts001.dampening_multiplier == 0.85
    assert ts001.final_score == 9.2


def test_no_compliance_penalises_deductions():
    """No compliance at all -> 1.30x penalty on deductions."""
    violations = [
        {"file": "a.ts", "line": 1, "snippet": "x", "reason": "r",
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
    assert ts001.dampening_multiplier == 1.30
    assert ts001.final_score == 8.7


def test_weak_compliance_ratio_penalises():
    """Compliance/violation ratio < 0.5 but > 0 -> 1.15x penalty."""
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
    assert ts001.dampening_multiplier == 1.15
    assert ts001.final_score == 8.8


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


def test_overall_low_confidence_when_most_insufficient():
    """Overall should be flagged low confidence when >50% principles are Insufficient."""
    pe_low1 = PrincipleEvidence(
        practice_id="p1", display_name="P1", dimension="security",
        severity="high", violations=[], compliance=[],
        metrics={"total_instances": 1, "compliant": 1, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "low", "is_balanced": False},
    )
    pe_low2 = PrincipleEvidence(
        practice_id="p2", display_name="P2", dimension="security",
        severity="high", violations=[], compliance=[],
        metrics={"total_instances": 1, "compliant": 1, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "low", "is_balanced": False},
    )
    pe_high = PrincipleEvidence(
        practice_id="p3", display_name="P3", dimension="security",
        severity="high", violations=[], compliance=[
            {"file": "a.ts", "line": 1, "snippet": "ok", "reason": "safe"},
        ],
        metrics={"total_instances": 10, "compliant": 10, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "high", "is_balanced": False},
    )
    ev = Evidence(
        repository="test", plugin_id="ts", date="2026-03-03",
        source_file_count=100, files_read=50, coverage_pct=50.0,
        principles={"p1": pe_low1, "p2": pe_low2, "p3": pe_high},
    )
    scores = score_evidence(ev, mode="numerical")
    assert scores.overall.confidence == "low"
    assert "1/3" in scores.overall.confidence_reason
