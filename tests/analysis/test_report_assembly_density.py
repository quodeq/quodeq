"""Report totals carry violationsPer100Files and meta carries unmappedTypes."""
from __future__ import annotations

from quodeq.analysis._report_assembly import _ReportData, _assemble_report_dict


def _violation(req, vt=None, vt_raw=None):
    v = {"file": "a.py", "line": 1, "severity": "minor", "req": req, "reason": "r"}
    if vt is not None:
        v["vt"] = vt
    if vt_raw is not None:
        v["vt_raw"] = vt_raw
    return v


def _data(violations, files_read=8):
    principles = {"Fault Tolerance": {"display_name": "Fault Tolerance", "violations": violations}}
    return _ReportData(
        dimension="reliability",
        evidence={"repository": "r", "files_read": files_read, "meta": {}, "principles": principles},
        top_score="8.0/10", top_grade="Good", principle_rows=[],
        flat_violations=list(violations), flat_compliance=[],
        sev_tally={"critical": 0, "major": 0, "minor": len(violations)},
    )


def test_totals_carry_violations_per_100_files():
    report = _assemble_report_dict(_data([_violation("R-FT-1", vt="x")] * 3, files_read=8))
    assert report["totals"]["violationsPer100Files"] == 37.5


def test_density_is_none_when_nothing_was_read():
    report = _assemble_report_dict(_data([_violation("R-FT-1", vt="x")], files_read=0))
    assert report["totals"]["violationsPer100Files"] is None


def test_unmapped_types_lists_untagged_and_other_by_requirement():
    violations = [
        _violation("R-FT-1"), _violation("R-FT-1"),                       # untagged x2
        _violation("R-FT-7", vt="other", vt_raw="weird-tag"),             # mapped to other
        _violation("R-FT-1", vt="empty-catch-block", vt_raw="Empty_Catch"),  # mapped: excluded
    ]
    report = _assemble_report_dict(_data(violations))
    assert report["meta"]["unmappedTypes"] == [
        {"req": "R-FT-1", "vtRaw": "", "count": 2},
        {"req": "R-FT-7", "vtRaw": "weird-tag", "count": 1},
    ]


def test_unmapped_types_is_capped_at_50_rows():
    report = _assemble_report_dict(_data([_violation(f"R-{i}") for i in range(60)]))
    assert len(report["meta"]["unmappedTypes"]) == 50


def test_unmapped_types_none_principles_is_treated_as_absent():
    data = _data([_violation("R-FT-1", vt="x")])
    data.evidence["principles"] = None
    report = _assemble_report_dict(data)
    assert report["meta"]["unmappedTypes"] == []


def test_unmapped_types_ties_are_ordered_by_key():
    violations = [
        _violation("R-B"),  # untagged, count 1
        _violation("R-A"),  # untagged, count 1
    ]
    report = _assemble_report_dict(_data(violations))
    assert report["meta"]["unmappedTypes"] == [
        {"req": "R-A", "vtRaw": "", "count": 1},
        {"req": "R-B", "vtRaw": "", "count": 1},
    ]
