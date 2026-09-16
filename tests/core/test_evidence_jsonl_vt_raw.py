"""vt_raw (the model's tag before taxonomy mapping) survives every core seam."""
from __future__ import annotations

import json

from quodeq.core.events.models import Judgment, JudgmentCreatedEvent
from quodeq.core.evidence._jsonl import judgment_to_dict, parse_jsonl_line
from quodeq.core.finding_mappings import judgment_to_finding, wire_dict_to_judgment
from quodeq.data.events.codec import event_from_dict, event_to_json


def _line(**extra) -> str:
    base = {
        "p": "Fault Tolerance", "t": "violation", "d": "reliability", "req": "R-FT-1",
        "file": "a.py", "line": 19, "severity": "minor", "w": "title", "reason": "why",
        "vt": "Empty_Catch",
    }
    base.update(extra)
    return json.dumps(base)


def test_parse_reads_vt_raw_and_leaves_vt_alone():
    judgment, _ = parse_jsonl_line(_line(vt_raw="Empty_Catch"))
    assert judgment.violation_type_raw == "Empty_Catch"
    assert judgment.violation_type == "Empty_Catch"


def test_parse_defaults_vt_raw_to_none():
    judgment, _ = parse_jsonl_line(_line())
    assert judgment.violation_type_raw is None


def test_judgment_to_dict_emits_vt_raw_only_when_set():
    tagged, _ = parse_jsonl_line(_line(vt_raw="Empty_Catch"))
    plain, _ = parse_jsonl_line(_line())
    assert judgment_to_dict(tagged)["vt_raw"] == "Empty_Catch"
    assert "vt_raw" not in judgment_to_dict(plain)


def test_wire_dict_and_finding_carry_vt_raw():
    j = wire_dict_to_judgment(json.loads(_line(vt_raw="Empty_Catch")))
    assert j.violation_type_raw == "Empty_Catch"
    assert judgment_to_finding(j).violation_type_raw == "Empty_Catch"
    assert wire_dict_to_judgment(json.loads(_line())).violation_type_raw is None
    assert wire_dict_to_judgment(json.loads(_line(vt_raw=""))).violation_type_raw is None


def test_event_codec_round_trips_and_tolerates_old_events():
    j = Judgment(practice_id="FT", verdict="violation", dimension="reliability",
                 file="a.py", line=1, reason="why", violation_type="x", violation_type_raw="X")
    raw = json.loads(event_to_json(JudgmentCreatedEvent(payload=j)))
    assert raw["payload"]["violation_type_raw"] == "X"
    assert event_from_dict(JudgmentCreatedEvent, raw).payload.violation_type_raw == "X"
    del raw["payload"]["violation_type_raw"]  # an events.jsonl written before this field
    assert event_from_dict(JudgmentCreatedEvent, raw).payload.violation_type_raw is None
