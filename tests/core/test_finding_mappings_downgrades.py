"""The provenance and scope downgrade markers survive every finding-shape conversion."""
from __future__ import annotations

from quodeq.core.events.models import Judgment
from quodeq.core.finding_mappings import judgment_to_finding, wire_dict_to_judgment


class TestProvenanceDowngradeField:
    """Issue #656: the provenance gate stamps ``provenance_downgrade`` on a
    finding dict it de-escalates. Promote it to a first-class field so it
    travels Judgment -> Finding -> API response, not just the JSONL forensic.
    """

    def test_wire_dict_carries_downgrade_marker(self):
        j = wire_dict_to_judgment({
            "p": "P1", "t": "violation", "d": "D", "file": "f", "line": 1,
            "reason": "r", "provenance_downgrade": True,
        })
        assert j.provenance_downgrade is True

    def test_wire_dict_defaults_downgrade_to_false_when_absent(self):
        j = wire_dict_to_judgment({"p": "P1", "t": "violation"})
        assert j.provenance_downgrade is False

    def test_judgment_to_finding_carries_downgrade(self):
        j = Judgment(
            practice_id="P1", verdict="violation", dimension="D",
            file="f", line=1, reason="r", provenance_downgrade=True,
        )
        f = judgment_to_finding(j)
        assert f.provenance_downgrade is True


class TestScopeDowngradeField:
    """The scope gate stamps ``scope_downgrade`` (a dict naming the rule,
    ``from`` and ``to`` severities) on a finding it caps from major to minor.
    Unlike ``provenance_downgrade`` (a bool), the whole point of this marker
    is to name WHICH rule moved it, so it must survive as a dict, not
    collapse to a boolean, at every seam it crosses.
    """

    def test_wire_dict_carries_downgrade_marker(self):
        j = wire_dict_to_judgment({
            "p": "P1", "t": "violation", "d": "D", "file": "f", "line": 1,
            "reason": "r",
            "scope_downgrade": {"rule": "sourceless_path", "from": "major", "to": "minor"},
        })
        assert j.scope_downgrade == {"rule": "sourceless_path", "from": "major", "to": "minor"}

    def test_wire_dict_defaults_downgrade_to_none_when_absent(self):
        j = wire_dict_to_judgment({"p": "P1", "t": "violation"})
        assert j.scope_downgrade is None

    def test_wire_dict_drops_malformed_scope_downgrade(self):
        # A non-dict value must never raise -- wire_dict_to_judgment's
        # documented contract is "never raises on malformed input".
        j = wire_dict_to_judgment({"p": "P1", "t": "violation", "scope_downgrade": "not-a-dict"})
        assert j.scope_downgrade is None

    def test_judgment_to_finding_carries_downgrade(self):
        j = Judgment(
            practice_id="P1", verdict="violation", dimension="D",
            file="f", line=1, reason="r",
            scope_downgrade={"rule": "cross_principal", "from": "major", "to": "minor"},
        )
        f = judgment_to_finding(j)
        assert f.scope_downgrade == {"rule": "cross_principal", "from": "major", "to": "minor"}
