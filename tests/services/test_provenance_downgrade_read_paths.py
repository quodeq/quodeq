"""provenance_downgrade must survive the evaluation/<dim>.json round trip.

``apply_provenance_gate`` stamps this marker when it de-escalates a critical
R-FT-2/S-AUT-3/S-INT-10 finding to major because the evidence names no external
source. The marker is the only record of WHY the severity moved, so a finding
that loses it is indistinguishable from an ordinary major.

Two boundaries have to agree, and neither raises when it disagrees:

  write  ``_flatten_findings`` copies ONLY the keys in ``_VIOLATION_FIELDS``
         into evaluation/<dim>.json -- a strict whitelist that silently drops
         anything unlisted.
  read   ``build_finding`` re-hydrates that JSON back into a ``Finding``, and
         only fields it explicitly names come back.

This mirrors tests/services/test_carried_forward_read_paths.py, which documents
the same bug class on the sibling marker: a gap in either parser makes the
marker vanish as a dimension finishes and its report is written.
"""
from __future__ import annotations

import json

from quodeq.analysis._report_assembly import build_report_json
from quodeq.analysis._report_constants import _VIOLATION_FIELDS
from quodeq.analysis._report_findings import _flatten_findings
from quodeq.analysis.mcp.provenance_gate import DOWNGRADE_MARKER
from quodeq.data.fs.report_parser._report_parsing import build_finding, parse_report_json


def _gated_finding() -> dict:
    """A finding shaped like one apply_provenance_gate has just downgraded."""
    return {
        "file": "a.py", "line": 7, "severity": "major", "req": "S-AUT-3",
        "title": "Path built from a filename argument with no bounds check.",
        "reason": "The path is assembled from a value with no named source.",
        DOWNGRADE_MARKER: True,
    }


def test_marker_survives_the_full_report_json_round_trip(tmp_path):
    """End-to-end: evidence -> evaluation/<dim>.json on disk -> parsed Finding.

    This is the path a dimension actually takes when it finishes, and it
    crosses BOTH the write whitelist and the read parser, so it fails if
    either one drops the marker.
    """
    evidence = {
        "principles": {
            "auth": {
                "display_name": "Access Control",
                "violations": [_gated_finding()],
                "compliance": [],
            },
        },
    }

    report = build_report_json("security", evidence, None)
    report_path = tmp_path / "security.json"
    report_path.write_text(json.dumps(report))

    parsed = parse_report_json(report_path)

    assert parsed is not None, "report must parse"
    assert len(parsed["violations"]) == 1
    assert parsed["violations"][0].provenance_downgrade is True, (
        "the provenance gate's downgrade marker must survive the "
        "evaluation/<dim>.json round trip, or a downgraded finding loses "
        "the record of why its severity moved"
    )


def test_report_write_whitelist_carries_the_marker_through_flatten():
    """_VIOLATION_FIELDS is a strict whitelist. Omission drops the marker
    silently -- no error, just a finding that forgot it was downgraded."""
    items = [
        _gated_finding(),
        {"file": "b.py", "line": 2, "severity": "major", "title": "t", "reason": "r"},
    ]

    flattened = _flatten_findings(items, "Access Control", _VIOLATION_FIELDS)

    downgraded, untouched = flattened
    assert downgraded[DOWNGRADE_MARKER] is True
    # A finding the gate never touched must not gain the key.
    assert DOWNGRADE_MARKER not in untouched


def test_report_json_read_path_carries_the_marker():
    item = {
        "principle": "Access Control", "file": "a.py", "line": 7,
        "severity": "major", "title": "t", "reason": "r",
        DOWNGRADE_MARKER: True,
    }
    assert build_finding(item, include_severity=True).provenance_downgrade is True


def test_report_json_read_path_defaults_to_false():
    item = {
        "principle": "Access Control", "file": "a.py", "line": 7,
        "severity": "major", "title": "t", "reason": "r",
    }
    assert build_finding(item, include_severity=True).provenance_downgrade is False
