"""_assemble_report_dict surfaces evidence.exit_reason as exitReason in the dict."""
from __future__ import annotations

from quodeq.analysis._report_assembly import _ReportData, _assemble_report_dict


def _evidence_dict(exit_reason: str | None) -> dict:
    return {
        "repository": "r", "discipline": "Python", "date": "2026-05-23",
        "source_file_count": 100, "files_read": 8, "coverage_pct": 8.0,
        "meta": {},
        "exit_reason": exit_reason,
    }


def test_report_dict_includes_exit_reason_when_set():
    data = _ReportData(
        dimension="security", evidence=_evidence_dict("time_limit"),
        top_score="5.7/10", top_grade="Poor",
        principle_rows=[], flat_violations=[], flat_compliance=[],
        sev_tally={"critical": 0, "major": 0, "minor": 0},
    )
    report = _assemble_report_dict(data)
    assert report["exitReason"] == "time_limit"


def test_report_dict_exit_reason_none_when_evidence_missing_field():
    data = _ReportData(
        dimension="security", evidence={**_evidence_dict(None)},
        top_score=None, top_grade=None,
        principle_rows=[], flat_violations=[], flat_compliance=[],
        sev_tally={"critical": 0, "major": 0, "minor": 0},
    )
    # Drop the key entirely
    data.evidence.pop("exit_reason")
    report = _assemble_report_dict(data)
    assert report.get("exitReason") is None
