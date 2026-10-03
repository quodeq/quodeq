"""parse_report_json preserves exitReason from the per-dim JSON, and must
tolerate malformed ``violations``/``compliance`` entries: a non-dict item
(or a non-list field entirely) is dropped, not indexed into."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.data.fs.report_parser._report_parsing import parse_report_json


def _base_report(**overrides) -> dict:
    report = {
        "schema_version": 1,
        "dimension": "security",
        "overallScore": "5.7/10",
        "overallGrade": "Poor",
        "principles": [],
        "violations": [],
        "compliance": [],
    }
    report.update(overrides)
    return report


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


def test_non_dict_violation_entries_are_dropped_and_warned(tmp_path: Path, caplog):
    json_path = tmp_path / "security.json"
    json_path.write_text(json.dumps(_base_report(
        violations=[{"principle": "p1", "file": "a.py"}, "not-a-dict", None, 42],
    )), encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="quodeq.data.fs.report_parser._report_parsing"):
        result = parse_report_json(json_path)

    assert result is not None
    assert len(result["violations"]) == 1
    assert "Dropped" in caplog.text


def test_non_list_violations_field_yields_no_findings(tmp_path: Path):
    """A whole-field type mismatch (e.g. a dict instead of a list) must
    degrade to no findings, not crash iterating over it."""
    json_path = tmp_path / "security.json"
    json_path.write_text(json.dumps(_base_report(violations={"oops": True})), encoding="utf-8")

    result = parse_report_json(json_path)

    assert result is not None
    assert result["violations"] == []


def test_non_dict_compliance_entries_are_dropped(tmp_path: Path):
    json_path = tmp_path / "security.json"
    json_path.write_text(json.dumps(_base_report(
        compliance=[{"principle": "p1"}, ["nested", "list"]],
    )), encoding="utf-8")

    result = parse_report_json(json_path)

    assert result is not None
    assert len(result["compliance"]) == 1


def test_well_formed_findings_are_unaffected(tmp_path: Path):
    json_path = tmp_path / "security.json"
    json_path.write_text(json.dumps(_base_report(
        violations=[{"principle": "p1", "file": "a.py"}],
        compliance=[{"principle": "p2", "file": "b.py"}],
    )), encoding="utf-8")

    result = parse_report_json(json_path)

    assert result is not None
    assert len(result["violations"]) == 1
    assert len(result["compliance"]) == 1
