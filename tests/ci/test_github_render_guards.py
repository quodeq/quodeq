"""Boundary guards for violation_to_comment: untrusted, schema-free LLM JSON.

Kept as its own file (rather than appended to test_review_builder.py) to
avoid pushing that file over the 300-line size ratchet.
"""
from __future__ import annotations

import pytest

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


def test_markdown_in_title_reason_and_req_is_escaped():
    # Titles/reasons come from LLM output that quotes PR content, so a crafted
    # finding could inject headings, links, or HTML into the review comment.
    from quodeq.ci.github_render import build_review_summary

    violation = {
        "file": "src/a.py",
        "line": 3,
        "severity": "minor",
        "title": "# Fake heading [link](https://evil.example) <img src=x>",
        "reason": "trailing `code` and **bold** and _em_",
        "req": "S-INT-9 | extra",
    }
    body = violation_to_comment(violation)["body"]
    assert body.startswith("🆕 NEW · **MINOR** — ")
    # Every control character is backslash-escaped, so GitHub renders it as
    # the literal character instead of a heading, link, tag, or emphasis.
    assert "\\# Fake heading \\[link\\](https://\u200bevil.example) \\<img src=x\\>" in body
    assert "trailing \\`code\\` and \\*\\*bold\\*\\* and \\_em\\_" in body
    assert "_Requirement: S-INT-9 \\| extra_" in body

    summary = build_review_summary(
        reports=[], new_violations=[violation], existing_violations=[],
        outside_diff_violations=[violation],
    )
    assert "\\[link\\](https://\u200bevil.example) \\<img src=x\\>" in summary


def test_plain_text_is_left_alone():
    violation = {"file": "a.py", "line": 1, "severity": "minor", "title": "Missing input validation", "req": "V5.1.1"}
    body = violation_to_comment(violation)["body"]
    assert "— Missing input validation" in body
    assert "_Requirement: V5.1.1_" in body


def test_bare_urls_and_mentions_do_not_autolink():
    # GitHub's extended-autolink and @mention scans run on rendered text, so a
    # backslash cannot defuse them; the trigger sequence itself must be broken.
    violation = {
        "file": "a.py", "line": 1, "severity": "minor",
        "title": "See https://evil.example/steal or www.evil.example",
        "reason": "ping @octocat too",
    }
    body = violation_to_comment(violation)["body"]
    assert "https://evil" not in body
    assert "www.evil" not in body
    assert "@octocat" not in body
    assert "evil.example/steal" in body  # only the trigger is broken, the text survives


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("- not a bullet", "\\- not a bullet"),
        ("+ not a bullet", "\\+ not a bullet"),
        ("1. not ordered", "1\\. not ordered"),
        ("2) not ordered", "2\\) not ordered"),
        ("--- not a rule", "\\--- not a rule"),
    ],
)
def test_reason_at_paragraph_start_cannot_open_a_block(reason, expected):
    # reason is its own paragraph, so a leading list or rule marker would
    # otherwise render as a bullet, an ordered item, or a horizontal rule.
    body = violation_to_comment({"file": "a.py", "line": 1, "severity": "minor", "title": "t", "reason": reason})["body"]
    assert "\n\n" + expected in body
