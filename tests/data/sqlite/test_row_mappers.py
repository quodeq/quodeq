import json
from quodeq.core.evidence.model import Judgment
from quodeq.data.sqlite._row_mappers import (
    finding_dict_to_row,
    row_to_judgment,
    judgment_to_row,
)


def test_finding_dict_to_row_maps_short_keys():
    finding = {
        "schema_version": 1,
        "p": "P-TIM-1",
        "d": "timeliness",
        "req": "REQ-1",
        "t": "violation",
        "severity": "high",
        "file": "src/x.py",
        "line": 10,
        "end_line": 12,
        "w": "Title here",
        "reason": "because",
        "snippet": "code",
        "violation_type": "missed_deadline",
        "context": "ctx",
        "scope": "scope",
        "req_refs": [{"id": "R1"}],
    }
    row = finding_dict_to_row(finding)
    assert row["practice_id"] == "P-TIM-1"
    assert row["dimension"] == "timeliness"
    assert row["requirement"] == "REQ-1"
    assert row["verdict"] == "violation"
    assert row["severity"] == "high"
    assert row["title"] == "Title here"
    assert row["dedup_key"] == "P-TIM-1|src/x.py|10|violation"
    assert json.loads(row["req_refs_json"]) == [{"id": "R1"}]


def test_finding_dict_to_row_handles_missing_optionals():
    finding = {"p": "P1", "t": "compliance", "severity": "low"}
    row = finding_dict_to_row(finding)
    assert row["file"] == ""
    assert row["line"] == 0
    assert row["req_refs_json"] is None
    assert row["dedup_key"] == "P1||0|compliance"


def test_row_to_judgment_roundtrip():
    finding = {
        "p": "P1", "d": "dim", "req": "R1", "t": "violation", "severity": "medium",
        "file": "f.py", "line": 5, "end_line": 8,
        "w": "T", "reason": "why", "snippet": "s",
    }
    row = finding_dict_to_row(finding)
    j = row_to_judgment(row)
    assert isinstance(j, Judgment)
    assert j.practice_id == "P1"
    assert j.dimension == "dim"
    assert j.req == "R1"
    assert j.verdict == "violation"
    assert j.line == 5
    assert j.title == "T"


def test_judgment_to_row_uses_long_names():
    j = Judgment(
        practice_id="P1", dimension="d", req="R1", verdict="violation",
        severity="high", file="f.py", line=3, title="t", reason="r", snippet="s",
    )
    row = judgment_to_row(j)
    assert row["practice_id"] == "P1"
    assert row["requirement"] == "R1"
    assert row["dedup_key"] == "P1|f.py|3|violation"


def test_finding_dict_to_row_defaults_confidence_to_100_when_missing():
    finding = {"p": "P1", "t": "violation", "severity": "medium"}
    row = finding_dict_to_row(finding)
    assert row["confidence"] == 100


def test_finding_dict_to_row_clamps_confidence_to_valid_range():
    assert finding_dict_to_row({"p": "P1", "t": "violation", "severity": "medium",
                                 "confidence": -50})["confidence"] == 0
    assert finding_dict_to_row({"p": "P1", "t": "violation", "severity": "medium",
                                 "confidence": 200})["confidence"] == 100
    assert finding_dict_to_row({"p": "P1", "t": "violation", "severity": "medium",
                                 "confidence": 73})["confidence"] == 73


def test_finding_dict_to_row_treats_non_int_confidence_as_default():
    row = finding_dict_to_row(
        {"p": "P1", "t": "violation", "severity": "medium", "confidence": "abc"},
    )
    assert row["confidence"] == 100


def test_judgment_to_row_propagates_confidence():
    j = Judgment(
        practice_id="P1", verdict="violation", severity="medium", confidence=42,
    )
    row = judgment_to_row(j)
    assert row["confidence"] == 42


def test_row_to_judgment_defaults_confidence_to_100_for_legacy_rows():
    # Older rows from before slice 1 lack the confidence column entirely.
    legacy_row = {
        "practice_id": "P1", "verdict": "violation", "severity": "medium",
        "file": "f.py", "line": 1,
    }
    j = row_to_judgment(legacy_row)
    assert j.confidence == 100


def test_row_to_judgment_preserves_explicit_confidence():
    row = {
        "practice_id": "P1", "verdict": "violation", "severity": "medium",
        "file": "f.py", "line": 1, "confidence": 30,
    }
    assert row_to_judgment(row).confidence == 30


from quodeq.core.events.models import JudgmentPayload
from quodeq.data.sqlite._row_mappers import judgment_payload_to_row


def test_judgment_payload_to_row_maps_required_fields():
    payload = JudgmentPayload(
        practice_id="P1",
        verdict="violation",
        dimension="Security",
        file="src/auth.py",
        line=42,
        reason="hardcoded secret",
    )
    row = judgment_payload_to_row(payload)
    assert row["practice_id"] == "P1"
    assert row["verdict"] == "violation"
    assert row["dimension"] == "Security"
    assert row["file"] == "src/auth.py"
    assert row["line"] == 42
    assert row["reason"] == "hardcoded secret"
    assert row["dedup_key"] == "P1|src/auth.py|42|violation"
    assert row["requirement"] is None
    assert row["end_line"] == 0


def test_judgment_payload_to_row_optional_fields_default():
    payload = JudgmentPayload(
        practice_id="P2", verdict="compliance", dimension="Reliability",
        file="f.py", line=1, reason="ok",
    )
    row = judgment_payload_to_row(payload)
    assert row["title"] == ""
    assert row["snippet"] == ""
    assert row["context"] == ""
    assert row["scope"] == ""
    assert row["violation_type"] == ""
    assert row["req_refs_json"] is None
    assert row["confidence"] == 100
    assert row["severity"] == "medium"
