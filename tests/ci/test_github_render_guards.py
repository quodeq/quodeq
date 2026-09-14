"""Boundary guards for violation_to_comment: untrusted, schema-free LLM JSON.

Kept as its own file (rather than appended to test_review_builder.py) to
avoid pushing that file over the 300-line size ratchet.
"""
from __future__ import annotations

from quodeq.ci.review_builder import violation_to_comment


def test_violation_missing_file_key_falls_back_to_placeholder():
    # Violation dicts come from LLM-produced JSON with no schema validation;
    # a missing "file" key must not KeyError and abort the whole build.
    violation = {
        "line": 10,
        "title": "Missing input validation",
        "reason": "no schema",
        "severity": "high",
        "req": "V5.1.1",
    }
    comment = violation_to_comment(violation)
    assert comment["path"] == "?"


def test_violation_non_numeric_line_coerces_to_zero_without_raising():
    # A non-numeric "line" used to raise inside int(line) and abort building
    # ALL PR review comments; it must now coerce to 0 like _coerce_line does.
    violation = {
        "file": "src/a.py",
        "line": "not-a-number",
        "title": "Bad line",
        "reason": "",
        "severity": "minor",
        "req": "",
    }
    comment = violation_to_comment(violation)
    assert comment["line"] == 0


def test_batch_with_one_bad_line_still_produces_all_comments():
    # Regression guard for the actual failure mode: previously one bad
    # violation's int(line) would raise and abort the whole PR review batch.
    violations = [
        {"file": "a.py", "line": 1, "title": "ok-1", "severity": "minor"},
        {"file": "b.py", "line": "garbage", "title": "bad-line", "severity": "minor"},
        {"file": "c.py", "line": 3, "title": "ok-2", "severity": "minor"},
    ]
    comments = [violation_to_comment(v) for v in violations]
    assert len(comments) == 3
    assert comments[0]["line"] == 1
    assert comments[1]["line"] == 0
    assert comments[2]["line"] == 3
