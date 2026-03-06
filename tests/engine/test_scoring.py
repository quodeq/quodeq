from __future__ import annotations

from codecompass.engine.evidence import Evidence, PrincipleEvidence
from codecompass.engine.scoring import score_evidence


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
            "confidence_level": "low",
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
