"""IncrementalTally: resumes a live evidence tally across appends.

Companion to test_evidence_tally.py's tally_unique_findings coverage --
IncrementalTally must always agree with a fresh tally_unique_findings over
the same bytes, whether reading forward from an offset or restarting from
zero after a rewrite.
"""
from __future__ import annotations

import json

from quodeq.data.fs.evidence_tally import IncrementalTally, tally_unique_findings


def _row(p, file, line, t="violation"):
    return json.dumps({"p": p, "file": file, "line": line, "t": t}) + "\n"


def test_advance_matches_a_full_tally_after_each_append(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(_row("P1", "a.py", 1) + _row("P1", "a.py", 1) + _row("P2", "b.py", 2, "compliance"))
    live = IncrementalTally(path)
    assert live.advance() == tally_unique_findings(path)
    with path.open("a") as f:
        f.write(_row("P1", "a.py", 1) + _row("P3", "c.py", 3))    # one more duplicate, one new violation
    assert live.advance() == tally_unique_findings(path)
    assert live.advance().duplicates == 2


def test_advance_reads_only_the_appended_bytes(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(_row("P1", "a.py", 1) + _row("P1", "a.py", 1) + _row("P2", "b.py", 2))
    live = IncrementalTally(path)

    first = live.advance()
    assert live.offset == path.stat().st_size
    assert first.duplicates == 1
    assert first.violations == 2

    with path.open("a") as f:
        f.write(_row("P3", "c.py", 3))
    second = live.advance()
    assert live.offset == path.stat().st_size
    # Carried over, not reset by the second advance re-reading from zero.
    assert second.duplicates == first.duplicates
    assert second.violations == 3


def test_a_partial_trailing_line_is_left_for_the_next_advance(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(_row("P1", "a.py", 1) + '{"p": "P2", "file": "b.py"')   # agent mid-write, no newline
    live = IncrementalTally(path)
    assert live.advance().violations == 1
    with path.open("a") as f:
        f.write(', "line": 2, "t": "violation"}\n')
    assert live.advance().violations == 2


def test_a_rewritten_file_is_tallied_from_scratch(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(_row("P1", "a.py", 1) * 3)
    live = IncrementalTally(path)
    assert live.advance().duplicates == 2
    path.write_text(_row("P1", "a.py", 1))            # the end-of-pool dedup pass rewrites in place, shorter
    assert live.advance() == tally_unique_findings(path)
    path.write_text(_row("P9", "z.py", 9) * 3)        # same byte length as the original 3 rows, different bytes
    assert live.advance() == tally_unique_findings(path)
