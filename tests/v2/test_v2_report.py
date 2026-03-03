from __future__ import annotations

import json
from pathlib import Path

from codecompass.v2.engine.evidence import Evidence, PrincipleEvidence
from codecompass.v2.engine.report import build_report, write_reports
from codecompass.v2.engine.scoring import score_evidence


def _make_evidence() -> Evidence:
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
        violations=[
            {"file": "a.ts", "line": 1, "snippet": "eval(x)", "reason": "injection", "severity": "high"},
        ],
        compliance=[
            {"file": "b.ts", "line": 2, "snippet": "JSON.parse(x)", "reason": "safe"},
        ],
        metrics={
            "total_instances": 2,
            "compliant": 1,
            "violating": 1,
            "compliance_percentage": 50.0,
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
        dismissed_count=2,
    )


def test_report_shape():
    ev = _make_evidence()
    scores = score_evidence(ev)
    report = build_report(ev, scores)
    assert "dimension" in report
    assert "principles" in report
    assert "violations" in report


def test_file_writing(tmp_path):
    ev = _make_evidence()
    scores = score_evidence(ev)
    write_reports(ev, scores, tmp_path)

    eval_file = tmp_path / "evaluation" / "security.json"
    evidence_file = tmp_path / "evidence" / "security_evidence.json"
    assert eval_file.exists()
    assert evidence_file.exists()

    eval_data = json.loads(eval_file.read_text())
    assert eval_data["dimension"] == "security"
    assert len(eval_data["principles"]) == 1

    ev_data = json.loads(evidence_file.read_text())
    assert "principles" in ev_data
    assert "ts-001" in ev_data["principles"]


def test_violations_structure():
    ev = _make_evidence()
    scores = score_evidence(ev)
    report = build_report(ev, scores)
    assert len(report["violations"]) == 1
    assert report["violations"][0]["principle"] == "Avoid eval()"
    assert report["violations"][0]["file"] == "a.ts"
