"""Tests for the centralized finding-shape conversions."""
from __future__ import annotations

from dataclasses import asdict

from quodeq.core.events.models import Judgment
from quodeq.core.finding_mappings import (
    finding_to_response_dict,
    judgment_to_finding,
    wire_dict_to_judgment,
)
from quodeq.core.types.finding import Finding
from quodeq.core.types.req_ref import ReqRef


class TestWireDictToJudgment:
    def test_short_keys_mapped_to_long_names(self):
        d = {
            "p": "P-TIM-1", "t": "violation", "d": "Timeliness",
            "w": "Missed deadline", "file": "src/x.py", "line": 10,
            "reason": "blocking call",
        }
        j = wire_dict_to_judgment(d)
        assert j.practice_id == "P-TIM-1"
        assert j.verdict == "violation"
        assert j.dimension == "Timeliness"
        assert j.title == "Missed deadline"
        assert j.file == "src/x.py"
        assert j.line == 10
        assert j.reason == "blocking call"

    def test_req_refs_dicts_converted_to_reqref_objects(self):
        d = {
            "p": "P1", "t": "violation", "d": "D", "file": "f.py", "line": 1,
            "reason": "r",
            "req_refs": [
                {"label": "CWE-798", "url": "https://cwe.mitre.org/798"},
                {"label": "OWASP-A1", "url": "https://owasp.org/A1"},
            ],
        }
        j = wire_dict_to_judgment(d)
        assert len(j.req_refs) == 2
        assert isinstance(j.req_refs[0], ReqRef)
        assert j.req_refs[0].label == "CWE-798"
        assert j.req_refs[0].url == "https://cwe.mitre.org/798"

    def test_missing_fields_get_safe_defaults(self):
        j = wire_dict_to_judgment({"p": "P1", "t": "compliance"})
        assert j.practice_id == "P1"
        assert j.verdict == "compliance"
        assert j.dimension == ""
        assert j.file == ""
        assert j.line == 0
        assert j.severity == "medium"
        assert j.confidence == 100
        assert j.req_refs == []

    def test_confidence_passed_through(self):
        j = wire_dict_to_judgment(
            {"p": "P1", "t": "violation", "d": "D", "file": "f", "line": 1,
             "reason": "r", "confidence": 50}
        )
        assert j.confidence == 50

    def test_malformed_line_falls_back_to_zero(self):
        """Regression: a non-numeric wire line must not raise -- the function
        documents that it never raises on malformed input."""
        j = wire_dict_to_judgment(
            {"p": "P1", "t": "violation", "line": "not-a-number"})
        assert j.line == 0

    def test_numeric_string_line_coerced(self):
        j = wire_dict_to_judgment({"p": "P1", "t": "violation", "line": "7"})
        assert j.line == 7

    def test_malformed_confidence_falls_back_to_100(self):
        j = wire_dict_to_judgment(
            {"p": "P1", "t": "violation", "confidence": "high"})
        assert j.confidence == 100

    def test_non_scalar_line_and_confidence_fall_back(self):
        j = wire_dict_to_judgment(
            {"p": "P1", "t": "violation", "line": [1, 2], "confidence": {"x": 1}})
        assert j.line == 0
        assert j.confidence == 100

    def test_violation_type_read_from_short_vt_key(self):
        """Regression: the JSONL wire format carries the taxonomy as 'vt'
        (see core/evidence/_jsonl.py); this reader must not silently drop it
        on the event-log/SQLite path when only the short key is present."""
        j = wire_dict_to_judgment(
            {"p": "P1", "t": "violation", "d": "D", "file": "f", "line": 1,
             "reason": "r", "vt": "code-injection"}
        )
        assert j.violation_type == "code-injection"

    def test_violation_type_read_from_long_key(self):
        j = wire_dict_to_judgment(
            {"p": "P1", "t": "violation", "d": "D", "file": "f", "line": 1,
             "reason": "r", "violation_type": "code-injection"}
        )
        assert j.violation_type == "code-injection"

    def test_round_trip_via_judgment_dump(self):
        """wire_dict → Judgment → dump preserves the long-name fields."""
        d = {"p": "P1", "t": "violation", "d": "D", "file": "f", "line": 1,
             "reason": "r", "w": "T"}
        j = wire_dict_to_judgment(d)
        dumped = asdict(j)
        assert dumped["practice_id"] == "P1"
        assert dumped["verdict"] == "violation"
        assert dumped["title"] == "T"


class TestJudgmentToFinding:
    def _judgment(self, **overrides):
        defaults = {
            "practice_id": "P1", "verdict": "violation", "dimension": "Security",
            "file": "src/auth.py", "line": 42, "reason": "hardcoded secret",
        }
        defaults.update(overrides)
        return Judgment(**defaults)

    def test_basic_projection(self):
        j = self._judgment(title="Hardcoded secret", confidence=80)
        f = judgment_to_finding(j)
        assert isinstance(f, Finding)
        assert f.practice_id == "P1"
        assert f.verdict == "violation"
        assert f.title == "Hardcoded secret"
        assert f.confidence == 80

    def test_dismissed_flag_overrides_verdict(self):
        j = self._judgment()
        f = judgment_to_finding(j, dismissed=True)
        assert f.verdict == "dismissed"

    def test_not_dismissed_preserves_verdict(self):
        j = self._judgment(verdict="compliance")
        f = judgment_to_finding(j, dismissed=False)
        assert f.verdict == "compliance"

    def test_req_refs_passed_through(self):
        refs = [ReqRef(label="CWE-1", url="https://x")]
        j = self._judgment(req_refs=refs)
        f = judgment_to_finding(j)
        assert f.req_refs == refs

    def test_severity_falls_back_to_minor(self):
        # Judgment defaults severity to "medium", but if some pathway produced
        # an empty severity, Finding's default should kick in.
        j = self._judgment(severity="")
        f = judgment_to_finding(j)
        assert f.severity == "minor"


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
