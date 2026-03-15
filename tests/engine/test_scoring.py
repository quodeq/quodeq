from __future__ import annotations

from quodeq.engine.evidence import Evidence, PrincipleEvidence
from quodeq.engine.scoring import score_evidence

from tests.engine.conftest import make_evidence_with_confidence


def _make_evidence(violations=None, compliance=None) -> Evidence:
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
        violations=violations or [
            {"file": "a.ts", "line": 1, "snippet": "eval(x)", "reason": "injection", "severity": "high", "vt": "code-injection"},
        ],
        compliance=compliance or [
            {"file": "b.ts", "line": 2, "snippet": "JSON.parse(x)", "reason": "safe"},
            {"file": "c.ts", "line": 3, "snippet": "JSON.parse(y)", "reason": "safe"},
        ],
        metrics={
            "total_instances": 3,
            "compliant": 2,
            "violating": 1,
            "compliance_percentage": 66.7,
            "confidence_level": "medium",
            "is_balanced": True,
        },
    )
    return Evidence(
        repository="test-repo",
        plugin_id="typescript",
        date="2026-03-03",
        source_file_count=100,
        files_read=50,
        coverage_pct=50.0,
        principles={"ts-001": pe},
    )


def test_numerical_scoring():
    ev = _make_evidence()
    scores = score_evidence(ev, mode="numerical")
    assert "principles" in scores
    assert "overall" in scores
    assert scores["mode"] == "numerical"
    ts001 = scores["principles"].get("ts-001")
    assert ts001 is not None
    assert "final_score" in ts001
    assert isinstance(ts001["final_score"], (int, float))


def test_non_numerical_grading():
    ev = _make_evidence()
    scores = score_evidence(ev, mode="non-numerical")
    assert scores["mode"] == "non-numerical"
    ts001 = scores["principles"].get("ts-001")
    assert ts001 is not None
    assert "grade" in ts001


def test_empty_evidence():
    ev = Evidence(
        repository="test",
        plugin_id="typescript",
        date="2026-03-03",
        source_file_count=0,
        files_read=0,
        coverage_pct=0.0,
    )
    scores = score_evidence(ev)
    assert scores["principles"] == {}
    assert scores["overall"]["weighted_score"] == 0.0


def test_scoring_structure():
    """Ensure scoring produces expected structure."""
    ev = _make_evidence()
    scores = score_evidence(ev)
    assert "repository" in scores
    assert "discipline" in scores
    assert "scale" in scores
    assert "tier" in scores["scale"]
    assert "multiplier" in scores["scale"]


# ---------------------------------------------------------------------------
# Deduction-only scoring model tests
# ---------------------------------------------------------------------------


def test_numerical_low_confidence_returns_insufficient():
    ev = make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["grade"] == "Insufficient"
    assert ts001["final_score"] == 0.0


def test_graded_low_confidence_returns_insufficient():
    ev = make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["grade"] == "Insufficient"


def test_numerical_high_confidence_no_violations():
    ev = make_evidence_with_confidence(
        confidence_level="high", violations=[], n_violations=0, n_compliance=10,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["base_score"] == 10
    assert ts001["final_score"] == 10.0
    assert ts001["grade"] == "Exemplary"


def test_numerical_high_confidence_with_violations():
    ev = make_evidence_with_confidence(
        confidence_level="high", n_violations=2, n_compliance=8,
        violations=[
            {"file": "a.ts", "line": 1, "snippet": "eval(x)", "reason": "r", "severity": "critical", "vt": "code-injection"},
            {"file": "b.ts", "line": 2, "snippet": "eval(y)", "reason": "r", "severity": "major", "vt": "unsafe-call"},
        ],
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["base_score"] == 10
    # 1 critical type (-2.0) + 1 major type (-1.0) = 3.0 raw deduction
    # compliance has no vt → 0 types via taxonomy → 1.30× penalty
    # 3.0 × 1.30 = 3.90 → 10 - 3.9 = 6.1
    assert ts001["dampening_multiplier"] == 1.30
    assert ts001["final_score"] == 6.1


def test_graded_high_confidence_no_violations():
    ev = make_evidence_with_confidence(
        confidence_level="high", violations=[], n_violations=0, n_compliance=10,
    )
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["base_grade"] == "Exemplary"
    assert ts001["grade"] == "Exemplary"


def test_weighted_overall_excludes_insufficient():
    """A mix of Insufficient and scored principles: overall uses only scored ones."""
    pe_low = PrincipleEvidence(
        practice_id="p-low", display_name="Low Conf", dimension="security",
        severity="high", violations=[], compliance=[],
        metrics={"total_instances": 1, "compliant": 1, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "low", "is_balanced": False},
    )
    pe_high = PrincipleEvidence(
        practice_id="p-high", display_name="High Conf", dimension="security",
        severity="high",
        violations=[{"file": "a.ts", "line": 1, "snippet": "x", "reason": "r", "severity": "critical", "vt": "vt1"}],
        compliance=[{"file": "b.ts", "line": 2, "snippet": "y", "reason": "r"}] * 9,
        metrics={"total_instances": 10, "compliant": 9, "violating": 1,
                 "compliance_percentage": 90.0, "confidence_level": "high", "is_balanced": True},
    )
    ev = Evidence(
        repository="test", plugin_id="ts", date="2026-03-03",
        source_file_count=100, files_read=50, coverage_pct=50.0,
        principles={"p-low": pe_low, "p-high": pe_high},
    )
    scores = score_evidence(ev, mode="numerical")
    assert scores["principles"]["p-low"]["grade"] == "Insufficient"
    # Overall should reflect only p-high, not be dragged down by p-low
    assert scores["overall"]["weighted_score"] == scores["principles"]["p-high"]["final_score"]


def test_all_insufficient_overall():
    ev = make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="numerical")
    assert scores["overall"]["grade"] == "Insufficient"
    assert scores["overall"]["weighted_score"] == 0.0
