"""parse_report_json preserves exitReason from the per-dim JSON."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.report_parser._report_parsing import parse_report_json


def test_parse_report_json_includes_exit_reason(tmp_path: Path):
    json_path = tmp_path / "security.json"
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "dimension": "security",
        "project": "r",
        "discipline": "Python",
        "date": "2026-05-23",
        "sourceFileCount": 100,
        "filesRead": 8,
        "coveragePct": 8.0,
        "exitReason": "time_limit",
        "meta": {},
        "overallScore": "5.7/10",
        "overallGrade": "Poor",
        "principles": [],
        "violations": [],
        "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
    }), encoding="utf-8")
    result = parse_report_json(json_path)
    assert result["exitReason"] == "time_limit"


def test_parse_report_json_exit_reason_none_when_absent(tmp_path: Path):
    json_path = tmp_path / "security.json"
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "dimension": "security",
        "project": "r",
        "discipline": "Python",
        "date": "2026-05-23",
        "sourceFileCount": 100,
        "filesRead": 8,
        "coveragePct": 8.0,
        "meta": {},
        "overallScore": "5.7/10",
        "overallGrade": "Poor",
        "principles": [],
        "violations": [],
        "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
    }), encoding="utf-8")
    result = parse_report_json(json_path)
    assert result.get("exitReason") is None
