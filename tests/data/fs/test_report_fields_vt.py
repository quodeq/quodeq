"""The report JSON keeps the ``vt`` tag the scorer groups by.

``evaluation/<dim>.json`` is a strict field whitelist. Without ``vt`` in it,
a reader of the report could not see what the scorer saw, which is how a
scoring change was once validated on the wrong artifact (issue #1274).
"""
from __future__ import annotations

from quodeq.data.fs.dimension_report.report_constants import COMPLIANCE_FIELDS, VIOLATION_FIELDS
from quodeq.data.fs.dimension_report.report_findings import flatten_findings

_ITEM = {"file": "a.py", "line": 1, "req": "M-MDF-1", "reason": "r", "vt": "magic-number",
         "severity": "minor"}


def test_violation_report_row_keeps_vt():
    (row,) = flatten_findings([_ITEM], "Modifiability", VIOLATION_FIELDS)
    assert row["vt"] == "magic-number"


def test_compliance_report_row_keeps_vt():
    (row,) = flatten_findings([_ITEM], "Modifiability", COMPLIANCE_FIELDS)
    assert row["vt"] == "magic-number"
