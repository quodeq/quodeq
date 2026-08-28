"""Every registered finding marker must survive every persistence boundary.

The class this closes (issue #1046): a marker is an additive field outside the
core finding schema, threaded by hand through a chain of serializers, and **no
boundary raises when one is missed**. ``_VIOLATION_FIELDS`` is a strict whitelist
that silently drops unknown keys; ``build_finding`` returns only fields it names.
A gap is invisible -- no error, no warning, just a finding that forgot why it was
downgraded.

It has happened once per marker that exists: ``carried_forward`` on the report
path, ``provenance_downgrade`` in ``_VIOLATION_FIELDS`` and ``build_finding``
(#1044), and ``scope_downgrade`` reaching the per-dim JSONL but never
``events.jsonl``. Three instances of one bug, each found and fixed alone.

So this is parametrized over :data:`PERSISTED_MARKERS` rather than written per
marker. Registering a marker opts it into every check below at once, which is
the point: the next marker's seams are forced closed when it is added instead of
after someone notices a finding lost its explanation.

The boundaries, and why each is here rather than covered by the round trip:

* ``_VIOLATION_FIELDS`` / ``build_finding`` -- the two ends of the
  ``evaluation/<dim>.json`` path. The round trip covers both, but a direct
  assertion names WHICH end broke instead of just that something did.
* ``Finding`` / ``FindingSpec`` -- the in-memory carrier. A marker with no field
  cannot be carried even when both parsers know it.
* ``Judgment`` -- the event payload written to ``events.jsonl``, which the SQL
  projection and the dashboard read. This is the one a report-path-only test
  misses: ``scope_downgrade`` cleared every other boundary while the dashboard
  still showed an unexplained minor.
* the round trip -- the boundaries composed, through a real file.
"""
from __future__ import annotations

import json

import pytest

from quodeq.analysis._report_assembly import build_report_json
from quodeq.analysis._report_constants import _VIOLATION_FIELDS
from quodeq.analysis._report_findings import _flatten_findings
from quodeq.core.events.models import Judgment
from quodeq.core.finding_builder import FindingSpec
from quodeq.core.finding_markers import PERSISTED_MARKERS
from quodeq.core.types import Finding
from quodeq.data.fs.report_parser._report_parsing import build_finding, parse_report_json


def _violation(marker=None) -> dict:
    """A violation dict, optionally carrying *marker* at its sample value."""
    item = {
        "principle": "Access Control", "file": "a.py", "line": 7,
        "severity": "major", "title": "t", "reason": "r",
    }
    if marker is not None:
        item[marker.name] = marker.sample
    return item


@pytest.mark.parametrize("marker", PERSISTED_MARKERS, ids=lambda m: m.name)
class TestMarkerSurvivesPersistence:
    def test_listed_in_violation_fields(self, marker):
        """_flatten_findings copies ONLY these keys into evaluation/<dim>.json."""
        assert marker.name in _VIOLATION_FIELDS

    def test_carried_by_finding(self, marker):
        assert marker.name in Finding.__dataclass_fields__

    def test_carried_by_finding_spec(self, marker):
        assert marker.name in FindingSpec.__dataclass_fields__

    def test_carried_by_judgment(self, marker):
        """The event payload written to events.jsonl.

        Not redundant with the report path: a marker can clear every other
        boundary and still never reach the SQL projection or the dashboard.
        """
        assert marker.name in Judgment.__dataclass_fields__

    def test_survives_the_write_whitelist(self, marker):
        flattened = _flatten_findings([_violation(marker)], "P1", _VIOLATION_FIELDS)
        assert flattened[0][marker.name] == marker.sample

    def test_read_back_by_build_finding(self, marker):
        finding = build_finding(_violation(marker), include_severity=True)
        assert getattr(finding, marker.name) == marker.sample

    def test_full_report_json_round_trip(self, marker, tmp_path):
        """evidence -> build_report_json -> real file -> parse_report_json."""
        evidence = {
            "principles": {
                "auth": {
                    "display_name": "Access Control",
                    "violations": [_violation(marker)],
                    "compliance": [],
                },
            },
        }
        report_path = tmp_path / "security.json"
        report_path.write_text(json.dumps(build_report_json("security", evidence, None)))

        parsed = parse_report_json(report_path)

        assert parsed is not None
        assert getattr(parsed["violations"][0], marker.name) == marker.sample

    def test_absent_marker_is_not_invented(self, marker):
        """A finding no producer stamped must not acquire the marker.

        Guards the other direction: a boundary that defaults to the sample
        value instead of an empty one would pass every test above.
        """
        flattened = _flatten_findings([_violation()], "P1", _VIOLATION_FIELDS)
        assert marker.name not in flattened[0]
        assert getattr(build_finding(_violation(), include_severity=True), marker.name) != marker.sample
