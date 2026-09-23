"""FindingType is the one home of "violation"/"compliance". Readers of stored
finding rows accept only the canonical spelling and never raise on junk; only
model output gets the case-and-space leniency (parse_finding_type)."""
from __future__ import annotations

import json

import pytest

from quodeq.core.events.models import Judgment
from quodeq.core.evidence.jsonl import parse_jsonl_line
from quodeq.core.types.finding_type import FINDING_TYPES, FindingType, parse_finding_type


def test_values_are_the_wire_spellings():
    assert {m.name: m.value for m in FindingType} == {"VIOLATION": "violation", "COMPLIANCE": "compliance"}
    assert FINDING_TYPES == (FindingType.VIOLATION, FindingType.COMPLIANCE)
    assert json.dumps({"t": FindingType.VIOLATION}) == '{"t": "violation"}'


@pytest.mark.parametrize(("raw", "expected"), [
    ("violation", FindingType.VIOLATION),
    (" Violation ", FindingType.VIOLATION),
    ("COMPLIANCE", FindingType.COMPLIANCE),
    ("violations", None),
    ("dismissed", None),
    ("", None),
    (None, None),
    (["violation"], None),
])
def test_parse_finding_type(raw, expected):
    assert parse_finding_type(raw) is expected


def _line(t: object) -> str:
    return json.dumps({"p": "M-MOD-1", "t": t, "file": "a.py", "line": 3, "reason": "r"})


def test_evidence_line_reader_keeps_the_canonical_spelling():
    parsed = parse_jsonl_line(_line("violation"))
    assert parsed is not None
    judgment, _refs = parsed
    assert judgment.verdict == FindingType.VIOLATION
    assert judgment.is_violation()


@pytest.mark.parametrize("t", ["Violation", "violations", ["violation"], {"t": 1}, None])
def test_evidence_line_reader_skips_other_spellings_without_raising(t):
    assert parse_jsonl_line(_line(t)) is None


def test_judgment_verdict_helpers_read_the_enum():
    j = Judgment(practice_id="M-MOD-1", verdict="compliance", dimension="d", file="a.py", line=1, reason="r")
    assert j.is_compliance()
    assert not j.is_violation()
    assert j.has_valid_verdict()
