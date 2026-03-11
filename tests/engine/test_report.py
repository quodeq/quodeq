from __future__ import annotations

import json
from pathlib import Path

from quodeq.engine.evidence import Evidence, PrincipleEvidence
from quodeq.engine.report import build_full_report, build_dashboard_report, write_reports
from quodeq.engine.scoring import score_evidence


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
        dismissed_count=2,
    )


def test_full_report_extra_fields():
    ev = _make_evidence()
    scores = score_evidence(ev)
    report = build_full_report(ev, scores)
    assert report["dismissed_count"] == 2
    assert "evidence_summary" in report
    assert report["evidence_summary"]["dismissed_count"] == 2


def test_dashboard_shape():
    ev = _make_evidence()
    scores = score_evidence(ev)
    report = build_dashboard_report(ev, scores)
    assert "dismissed_count" not in report
    assert "dimension" in report
    assert "principles" in report
    assert "violations" in report


def test_file_writing(tmp_path):
    ev = _make_evidence()
    scores = score_evidence(ev)
    write_reports(ev, scores, tmp_path)

    full_file = tmp_path / "typescript_full.json"
    dashboard_file = tmp_path / "typescript.json"
    assert full_file.exists()
    assert dashboard_file.exists()

    full_data = json.loads(full_file.read_text())
    dashboard_data = json.loads(dashboard_file.read_text())

    assert "dismissed_count" in full_data
    assert "dismissed_count" not in dashboard_data


def test_violations_structure():
    ev = _make_evidence()
    scores = score_evidence(ev)
    report = build_full_report(ev, scores)
    assert len(report["violations"]) == 1
    assert report["violations"][0]["principle"] == "Avoid eval()"
    assert report["violations"][0]["file"] == "a.ts"
