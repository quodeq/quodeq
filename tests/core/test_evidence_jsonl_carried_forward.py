"""carried_forward must survive the JSONL <-> Judgment round trip.

The live evaluation feed hides findings replayed from the incremental
cache. The marker is stamped at replay time and read back here; if this
seam drops it, every carried finding reads as new and the filter is inert.
"""
import json

from quodeq.core.evidence._jsonl import judgment_to_dict, parse_jsonl_line
from quodeq.core.finding_mappings import wire_dict_to_judgment


def _line(**extra) -> str:
    base = {
        "p": "M-MOD-12", "t": "violation", "d": "maintainability",
        "file": "a.py", "line": 19, "severity": "minor",
        "w": "title", "reason": "why",
    }
    base.update(extra)
    return json.dumps(base)


def test_parse_reads_carried_forward():
    judgment, _refs = parse_jsonl_line(_line(carried_forward=True))
    assert judgment.carried_forward is True


def test_parse_defaults_carried_forward_to_false():
    judgment, _refs = parse_jsonl_line(_line())
    assert judgment.carried_forward is False


def test_judgment_to_dict_emits_flag_only_when_set():
    carried, _ = parse_jsonl_line(_line(carried_forward=True))
    fresh, _ = parse_jsonl_line(_line())
    assert judgment_to_dict(carried)["carried_forward"] is True
    # Absent, not False: keeps the common-case dict compact, mirroring
    # how confidence and provenance_downgrade are handled.
    assert "carried_forward" not in judgment_to_dict(fresh)


def test_wire_dict_to_judgment_reads_carried_forward():
    # Used by _emit_cached_findings to mirror cache replays into
    # events.jsonl, which feeds the SSE path.
    assert wire_dict_to_judgment(
        json.loads(_line(carried_forward=True))
    ).carried_forward is True
