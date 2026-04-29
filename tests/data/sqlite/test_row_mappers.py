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
