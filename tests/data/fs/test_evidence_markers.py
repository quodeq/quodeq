"""Characterization for tally_evidence_markers: (ok, error) file_done counts
from a dim's evidence JSONL.

Pins the edge cases Review Focus 5 names before/after the R5a move from
``analysis._loop_guards._tally_markers``: latest-status-wins per file, a
corrupt JSON line is skipped, a non-UTF8 line degrades via
``errors="replace"`` instead of raising, and a missing/empty file yields
``(0, 0)``.
"""
from __future__ import annotations

import json

from quodeq.data.fs.evidence_markers import tally_evidence_markers


def _write_markers(path, markers: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for file, status in markers:
            fh.write(json.dumps({"_marker": "file_done", "file": file, "status": status}) + "\n")


class TestTallyEvidenceMarkers:
    def test_latest_status_per_file_wins(self, tmp_path):
        """A file that errored then later succeeded counts as ok, not both."""
        path = tmp_path / "d_evidence.jsonl"
        _write_markers(path, [("a.py", "error"), ("a.py", "ok"), ("b.py", "ok")])
        assert tally_evidence_markers(path) == (2, 0)

    def test_latest_status_can_flip_to_error(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        _write_markers(path, [("a.py", "ok"), ("a.py", "error")])
        assert tally_evidence_markers(path) == (0, 1)

    def test_corrupt_json_line_is_skipped(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text(
            '{"_marker": "file_done", "file": "a.py", "status": "ok"}\n'
            "{not valid json\n"
            '{"_marker": "file_done", "file": "b.py", "status": "error"}\n',
            encoding="utf-8",
        )
        assert tally_evidence_markers(path) == (1, 1)

    def test_non_utf8_line_decodes_with_errors_replace(self, tmp_path):
        """A non-UTF8 byte sequence degrades to an unparseable line (dropped
        by the JSON guard) instead of raising UnicodeDecodeError."""
        path = tmp_path / "d_evidence.jsonl"
        good = json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}).encode()
        path.write_bytes(good + b"\n" + b"\xff\xfe not valid utf8\n")
        assert tally_evidence_markers(path) == (1, 0)

    def test_missing_file_returns_zero_zero(self, tmp_path):
        assert tally_evidence_markers(tmp_path / "missing.jsonl") == (0, 0)

    def test_empty_file_returns_zero_zero(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text("", encoding="utf-8")
        assert tally_evidence_markers(path) == (0, 0)

    def test_blank_lines_are_ignored(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text(
            "\n   \n" + json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n",
            encoding="utf-8",
        )
        assert tally_evidence_markers(path) == (1, 0)

    def test_non_marker_rows_and_skipped_status_are_ignored(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text(
            json.dumps({"p": "P1", "t": "violation"}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "a.py", "status": "skipped"}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n",
            encoding="utf-8",
        )
        assert tally_evidence_markers(path) == (1, 0)
