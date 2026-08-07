"""carried_forward must reach the API on BOTH dimension-eval read paths.

resolve_dimension_eval prefers evaluation/<dim>.json and falls back to the
evidence JSONL. A running dimension has only the JSONL; a finished one has
the JSON. The live feed crosses that boundary mid-run, so a gap in either
parser makes carried findings reappear as each dimension completes.
"""
from quodeq.analysis._report_constants import _VIOLATION_FIELDS
from quodeq.analysis._report_findings import _flatten_findings
from quodeq.data.fs.report_parser._report_parsing import build_finding
from quodeq.services.violations_parsing import _build_finding_entry


def test_live_jsonl_path_carries_the_flag():
    obj = {
        "p": "P1", "t": "violation", "d": "security", "file": "a.py",
        "line": 1, "severity": "minor", "w": "t", "reason": "r",
        "carried_forward": True,
    }
    assert _build_finding_entry(obj, "security").carried_forward is True


def test_live_jsonl_path_defaults_to_false():
    obj = {
        "p": "P1", "t": "violation", "d": "security", "file": "a.py",
        "line": 1, "severity": "minor", "w": "t", "reason": "r",
    }
    assert _build_finding_entry(obj, "security").carried_forward is False


def test_report_json_path_carries_the_flag():
    item = {
        "principle": "P1", "file": "a.py", "line": 1, "severity": "minor",
        "title": "t", "reason": "r", "carried_forward": True,
    }
    assert build_finding(item, include_severity=True).carried_forward is True


def test_report_write_whitelist_carries_the_flag_through_flatten():
    """_flatten_findings keeps ONLY the keys listed in _VIOLATION_FIELDS when
    writing evaluation/<dim>.json. Omission here drops the flag silently."""
    items = [
        {
            "file": "a.py", "line": 1, "severity": "minor",
            "title": "t", "reason": "r", "carried_forward": True,
        },
        {
            "file": "b.py", "line": 2, "severity": "minor",
            "title": "t", "reason": "r",
        },
    ]

    flattened = _flatten_findings(items, "P1", _VIOLATION_FIELDS)

    carried, not_carried = flattened
    assert carried["carried_forward"] is True
    assert "carried_forward" not in not_carried


# ---------------------------------------------------------------------------
# scope_downgrade must survive BOTH dimension-eval read paths too, the same
# class of bug carried_forward guards above: a gap in either parser makes a
# gated finding's rule name reappear/disappear as a dimension finishes.
# ---------------------------------------------------------------------------

def test_live_jsonl_path_carries_scope_downgrade():
    marker = {"rule": "sourceless_path", "from": "major", "to": "minor"}
    obj = {
        "p": "P1", "t": "violation", "d": "security", "file": "a.py",
        "line": 1, "severity": "minor", "w": "t", "reason": "r",
        "scope_downgrade": marker,
    }
    assert _build_finding_entry(obj, "security").scope_downgrade == marker


def test_live_jsonl_path_defaults_scope_downgrade_to_none():
    obj = {
        "p": "P1", "t": "violation", "d": "security", "file": "a.py",
        "line": 1, "severity": "minor", "w": "t", "reason": "r",
    }
    assert _build_finding_entry(obj, "security").scope_downgrade is None


def test_report_json_path_carries_scope_downgrade():
    marker = {"rule": "sourceless_path", "from": "major", "to": "minor"}
    item = {
        "principle": "P1", "file": "a.py", "line": 1, "severity": "minor",
        "title": "t", "reason": "r", "scope_downgrade": marker,
    }
    assert build_finding(item, include_severity=True).scope_downgrade == marker


def test_report_write_whitelist_carries_scope_downgrade_through_flatten():
    """Same whitelist gap class as carried_forward above: _flatten_findings
    keeps ONLY the keys listed in _VIOLATION_FIELDS when writing
    evaluation/<dim>.json. Omission here drops the rule name silently, and a
    reader could no longer tell a waived finding from an ordinary minor."""
    marker = {"rule": "sourceless_path", "from": "major", "to": "minor"}
    items = [
        {
            "file": "a.py", "line": 1, "severity": "minor",
            "title": "t", "reason": "r", "scope_downgrade": marker,
        },
        {
            "file": "b.py", "line": 2, "severity": "minor",
            "title": "t", "reason": "r",
        },
    ]

    flattened = _flatten_findings(items, "P1", _VIOLATION_FIELDS)

    downgraded, not_downgraded = flattened
    assert downgraded["scope_downgrade"] == marker
    assert "scope_downgrade" not in not_downgraded
