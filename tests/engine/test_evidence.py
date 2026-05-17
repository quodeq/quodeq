from __future__ import annotations

from quodeq.core.evidence.model import Evidence, Judgment, PrincipleEvidence


def test_judgment_defaults():
    j = Judgment(
        practice_id="ts-001", verdict="violation", dimension="security",
        file="a.py", line=1, reason="r",
    )
    assert j.verdict == "violation"
    assert j.severity == "medium"
    assert j.confidence == 100
    assert j.req_refs == []
    assert j.is_violation() is True


def test_principle_evidence_compute_metrics():
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
    )
    pe.add_violations([{"file": "a.ts", "line": 1}])
    pe.add_compliance([{"file": "b.ts", "line": 2}, {"file": "c.ts", "line": 3}])

    assert pe.metrics["total_instances"] == 3
    assert pe.metrics["compliant"] == 2
    assert pe.metrics["violating"] == 1
    assert pe.metrics["compliance_percentage"] == 66.7
    assert pe.metrics["is_balanced"] is True
    assert pe.metrics["confidence_level"] == "low"  # 3 < 5


def test_principle_evidence_unbalanced():
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Test",
        dimension="security",
        severity="high",
    )
    pe.add_violations([{"file": "a.ts"} for _ in range(5)])
    assert pe.metrics["is_balanced"] is False


def test_evidence_summary():
    pe1 = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Test1",
        dimension="security",
        severity="high",
        metrics={"total_instances": 10, "confidence_level": "high", "is_balanced": True},
    )
    pe2 = PrincipleEvidence(
        practice_id="ts-002",
        display_name="Test2",
        dimension="maintainability",
        severity="medium",
        metrics={"total_instances": 2, "confidence_level": "low", "is_balanced": False},
    )
    ev = Evidence(
        repository="test-repo",
        language="typescript",
        date="2026-03-03",
        source_file_count=100,
        files_read=50,
        coverage_pct=50.0,
        principles={"ts-001": pe1, "ts-002": pe2},
        dismissed_count=3,
    )
    s = ev.summary()
    assert s["total_findings"] == 12
    assert s["principles_count"] == 2
    assert s["dismissed_count"] == 3
    assert "ts-002" in s["low_confidence_principles"]
    assert "ts-002" in s["unbalanced_principles"]


def test_evidence_to_v1_dict():
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
        violations=[{"file": "a.ts", "line": 1, "snippet": "eval(x)", "reason": "injection", "severity": "high"}],
        compliance=[{"file": "b.ts", "line": 2, "snippet": "JSON.parse(x)", "reason": "safe parsing"}],
        metrics={"total_instances": 2, "compliant": 1, "violating": 1,
                 "compliance_percentage": 50.0, "confidence_level": "low", "is_balanced": True},
    )
    ev = Evidence(
        repository="test-repo",
        language="typescript",
        date="2026-03-03",
        source_file_count=100,
        files_read=50,
        coverage_pct=50.0,
        principles={"ts-001": pe},
    )
    d = ev.to_evidence_dict()
    assert d["repository"] == "test-repo"
    assert d["discipline"] == "Typescript"
    assert "ts-001" in d["principles"]
    assert d["principles"]["ts-001"]["violations"][0]["severity"] == "high"
    assert d["source_file_count"] == 100
    assert d["files_read"] == 50
