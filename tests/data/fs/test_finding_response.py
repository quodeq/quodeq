"""Tests for the Finding -> SSE/REST response dict shape."""
from __future__ import annotations

from quodeq.core.finding_mappings import judgment_to_finding, wire_dict_to_judgment
from quodeq.core.types.finding import Finding
from quodeq.core.types.req_ref import ReqRef
from quodeq.data.fs.report_parser.finding_response import finding_to_response_dict


def test_key_order_is_frozen():
    f = Finding(practice_id="P", file="a.py", line=1, verdict="violation", severity="minor")
    assert list(finding_to_response_dict(f)) == [
        "practice_id", "file", "line", "end_line", "snippet", "verdict", "severity",
        "reason", "title", "req", "req_refs", "provenance_downgrade", "scope_downgrade",
    ]


class TestFindingToResponseDict:
    def _finding(self, **overrides):
        defaults = {
            "practice_id": "P1", "verdict": "violation", "file": "src/auth.py",
            "line": 42, "reason": "hardcoded secret", "title": "Secret",
            "severity": "high",
        }
        defaults.update(overrides)
        return Finding(**defaults)

    def test_shape_matches_legacy_evidence_dict(self):
        f = self._finding(snippet="API_KEY = 'abc'", end_line=42)
        d = finding_to_response_dict(f)
        assert d["practice_id"] == "P1"
        assert d["file"] == "src/auth.py"
        assert d["line"] == 42
        assert d["end_line"] == 42
        assert d["snippet"] == "API_KEY = 'abc'"

    def test_shape_includes_verdict_and_text_fields(self):
        f = self._finding(snippet="API_KEY = 'abc'", end_line=42)
        d = finding_to_response_dict(f)
        assert d["verdict"] == "violation"
        assert d["severity"] == "high"
        assert d["title"] == "Secret"
        assert d["reason"] == "hardcoded secret"

    def test_req_refs_serialized_as_dicts(self):
        refs = [ReqRef(label="CWE-798", url="https://x"),
                ReqRef(label="OWASP", url="https://y")]
        f = self._finding(req_refs=refs)
        d = finding_to_response_dict(f)
        assert d["req_refs"] == [
            {"label": "CWE-798", "url": "https://x"},
            {"label": "OWASP", "url": "https://y"},
        ]

    def test_empty_req_refs_render_as_none(self):
        f = self._finding()
        d = finding_to_response_dict(f)
        assert d["req_refs"] is None


class TestRoundTrip:
    def test_wire_dict_to_finding_via_judgment(self):
        d = {
            "p": "P1", "t": "violation", "d": "Security",
            "file": "auth.py", "line": 1, "reason": "r",
            "w": "Title",
            "req_refs": [{"label": "CWE-1", "url": "https://x"}],
        }
        j = wire_dict_to_judgment(d)
        f = judgment_to_finding(j)
        response = finding_to_response_dict(f)
        assert response["practice_id"] == "P1"
        assert response["title"] == "Title"
        assert response["req_refs"] == [{"label": "CWE-1", "url": "https://x"}]


class TestProvenanceDowngradeField:
    """Issue #656: the provenance gate stamps ``provenance_downgrade`` on a
    finding dict it de-escalates. Promote it to a first-class field so it
    travels Judgment -> Finding -> API response, not just the JSONL forensic.
    """

    def test_finding_to_response_dict_includes_downgrade(self):
        f = Finding(
            practice_id="P1", verdict="violation", file="f", line=1,
            reason="r", severity="major", provenance_downgrade=True,
        )
        assert finding_to_response_dict(f)["provenance_downgrade"] is True

    def test_response_dict_downgrade_false_by_default(self):
        f = Finding(practice_id="P1", verdict="violation", file="f", line=1)
        assert finding_to_response_dict(f)["provenance_downgrade"] is False


class TestScopeDowngradeField:
    """The scope gate stamps ``scope_downgrade`` (a dict naming the rule,
    ``from`` and ``to`` severities) on a finding it caps from major to minor.
    Unlike ``provenance_downgrade`` (a bool), the whole point of this marker
    is to name WHICH rule moved it, so it must survive as a dict, not
    collapse to a boolean, at every seam it crosses.
    """

    def test_finding_to_response_dict_includes_downgrade(self):
        f = Finding(
            practice_id="P1", verdict="violation", file="f", line=1,
            reason="r", severity="minor",
            scope_downgrade={"rule": "sourceless_path", "from": "major", "to": "minor"},
        )
        assert finding_to_response_dict(f)["scope_downgrade"] == {
            "rule": "sourceless_path", "from": "major", "to": "minor",
        }

    def test_response_dict_downgrade_none_by_default(self):
        f = Finding(practice_id="P1", verdict="violation", file="f", line=1)
        assert finding_to_response_dict(f)["scope_downgrade"] is None

    def test_round_trip_names_the_rule(self):
        """Full wire -> Judgment -> Finding -> response round trip must still
        name the rule -- a marker that only says "something moved this" does
        not let anyone recover what was waived."""
        d = {
            "p": "P1", "t": "violation", "d": "Security", "file": "f", "line": 1,
            "reason": "r", "severity": "minor",
            "scope_downgrade": {"rule": "sourceless_path", "from": "major", "to": "minor"},
        }
        j = wire_dict_to_judgment(d)
        f = judgment_to_finding(j)
        response = finding_to_response_dict(f)
        assert response["scope_downgrade"]["rule"] == "sourceless_path"
        assert response["scope_downgrade"]["from"] == "major"
