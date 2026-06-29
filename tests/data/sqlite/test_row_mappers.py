import json
from quodeq.core.events.models import Judgment
from quodeq.data.sqlite._row_mappers import (
    finding_dict_to_row,
    judgment_to_row,
    row_to_finding,
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


def test_finding_dict_to_row_reads_violation_type_from_short_vt_key():
    """Regression: the JSONL wire format carries the taxonomy as 'vt'
    (see core/evidence/_jsonl.py); the row mapper must accept both keys."""
    finding = {"p": "P1", "t": "violation", "severity": "medium",
               "vt": "missed_deadline"}
    row = finding_dict_to_row(finding)
    assert row["violation_type"] == "missed_deadline"


def test_finding_dict_to_row_reads_violation_type_from_long_key():
    finding = {"p": "P1", "t": "violation", "severity": "medium",
               "violation_type": "missed_deadline"}
    row = finding_dict_to_row(finding)
    assert row["violation_type"] == "missed_deadline"


def test_row_to_finding_roundtrip():
    finding = {
        "p": "P1", "d": "dim", "req": "R1", "t": "violation", "severity": "medium",
        "file": "f.py", "line": 5, "end_line": 8,
        "w": "T", "reason": "why", "snippet": "s",
    }
    row = finding_dict_to_row(finding)
    f = row_to_finding(row)
    from quodeq.core.types.finding import Finding
    assert isinstance(f, Finding)
    assert f.practice_id == "P1"
    assert f.dimension == "dim"
    assert f.req == "R1"
    assert f.verdict == "violation"
    assert f.line == 5
    assert f.title == "T"


def test_judgment_to_row_uses_long_names():
    j = Judgment(
        practice_id="P1", dimension="d", req="R1", verdict="violation",
        severity="high", file="f.py", line=3, title="t", reason="r", snippet="s",
    )
    row = judgment_to_row(j)
    assert row["practice_id"] == "P1"
    assert row["requirement"] == "R1"
    assert row["title"] == "t"
    assert row["snippet"] == "s"
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
        practice_id="P1", verdict="violation", dimension="d",
        file="f.py", line=1, reason="r",
        severity="medium", confidence=42,
    )
    row = judgment_to_row(j)
    assert row["confidence"] == 42


def test_row_to_finding_defaults_confidence_to_100_for_legacy_rows():
    # Older rows from before slice 1 lack the confidence column entirely.
    legacy_row = {
        "practice_id": "P1", "verdict": "violation", "severity": "medium",
        "file": "f.py", "line": 1,
    }
    j = row_to_finding(legacy_row)
    assert j.confidence == 100


def test_row_to_finding_preserves_explicit_confidence():
    row = {
        "practice_id": "P1", "verdict": "violation", "severity": "medium",
        "file": "f.py", "line": 1, "confidence": 30,
    }
    assert row_to_finding(row).confidence == 30


def test_finding_dict_to_row_sets_provenance_downgrade_flag():
    # Issue #656: the gate stamps provenance_downgrade=True on dicts it
    # de-escalates; persist it as 1/0 so the SQL projection can surface it.
    on = finding_dict_to_row({"p": "P1", "t": "violation", "severity": "major",
                              "provenance_downgrade": True})
    assert on["provenance_downgrade"] == 1
    off = finding_dict_to_row({"p": "P1", "t": "violation", "severity": "major"})
    assert off["provenance_downgrade"] == 0


def test_judgment_to_row_sets_provenance_downgrade_flag():
    j = Judgment(
        practice_id="P1", verdict="violation", dimension="d",
        file="f.py", line=1, reason="r", severity="major",
        provenance_downgrade=True,
    )
    assert judgment_to_row(j)["provenance_downgrade"] == 1


def test_row_to_finding_reads_provenance_downgrade_flag():
    assert row_to_finding({
        "practice_id": "P1", "verdict": "violation", "severity": "major",
        "file": "f.py", "line": 1, "provenance_downgrade": 1,
    }).provenance_downgrade is True
    # Legacy rows (pre-#656, no column) default to False.
    assert row_to_finding({
        "practice_id": "P1", "verdict": "violation", "severity": "major",
        "file": "f.py", "line": 1,
    }).provenance_downgrade is False


def test_judgment_to_row_maps_required_fields():
    payload = Judgment(
        practice_id="P1",
        verdict="violation",
        dimension="Security",
        file="src/auth.py",
        line=42,
        reason="hardcoded secret",
    )
    row = judgment_to_row(payload)
    assert row["practice_id"] == "P1"
    assert row["verdict"] == "violation"
    assert row["dimension"] == "Security"
    assert row["file"] == "src/auth.py"
    assert row["line"] == 42
    assert row["reason"] == "hardcoded secret"
    assert row["dedup_key"] == "P1|src/auth.py|42|violation"
    assert row["requirement"] is None
    assert row["end_line"] == 0


def test_judgment_to_row_optional_fields_default():
    payload = Judgment(
        practice_id="P2", verdict="compliance", dimension="Reliability",
        file="f.py", line=1, reason="ok",
    )
    row = judgment_to_row(payload)
    assert row["title"] == ""
    assert row["snippet"] == ""
    assert row["context"] == ""
    assert row["scope"] == ""
    assert row["violation_type"] == ""
    assert row["req_refs_json"] == "[]"
    assert row["confidence"] == 100
    assert row["severity"] == "medium"
