"""Tests for subagents/jsonl_utils.py — dedup, merge, edge cases."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.subagents.jsonl_utils import (
    dedup_jsonl_lines,
    deduplicate_jsonl,
    merge_jsonl,
)


# ---------------------------------------------------------------------------
# dedup_jsonl_lines
# ---------------------------------------------------------------------------

class TestDedupJsonlLines:
    def test_removes_duplicates(self):
        lines = [
            json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "violation"}),
            json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "violation"}),
            json.dumps({"p": "P2", "file": "b.py", "line": 2, "t": "compliance"}),
        ]
        result = dedup_jsonl_lines(lines)
        assert len(result) == 2

    def test_keeps_unique_lines(self):
        lines = [
            json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "violation"}),
            json.dumps({"p": "P1", "file": "a.py", "line": 2, "t": "violation"}),
            json.dumps({"p": "P2", "file": "a.py", "line": 1, "t": "violation"}),
        ]
        result = dedup_jsonl_lines(lines)
        assert len(result) == 3

    def test_skips_empty_lines(self):
        lines = ["", "  ", json.dumps({"p": "X", "file": "a.py", "line": 1, "t": "v"})]
        result = dedup_jsonl_lines(lines)
        assert len(result) == 1

    def test_skips_malformed_json(self):
        lines = [
            "not valid json",
            json.dumps({"p": "X", "file": "a.py", "line": 1, "t": "v"}),
        ]
        result = dedup_jsonl_lines(lines)
        assert len(result) == 1

    def test_empty_input(self):
        assert dedup_jsonl_lines([]) == []

    def test_dedup_key_includes_all_four_fields(self):
        """Same file/line/t but different p should be kept."""
        lines = [
            json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "violation"}),
            json.dumps({"p": "P2", "file": "a.py", "line": 1, "t": "violation"}),
        ]
        result = dedup_jsonl_lines(lines)
        assert len(result) == 2

    def test_missing_key_fields_treated_as_none(self):
        """Lines missing dedup key fields should still work (None keys)."""
        lines = [
            json.dumps({"extra": "data1"}),
            json.dumps({"extra": "data2"}),
        ]
        # Both have key (None, None, None, None) so second is a dup
        result = dedup_jsonl_lines(lines)
        assert len(result) == 1

    def test_strips_whitespace(self):
        line = json.dumps({"p": "X", "file": "a.py", "line": 1, "t": "v"})
        lines = [f"  {line}  "]
        result = dedup_jsonl_lines(lines)
        assert len(result) == 1
        # Should be stripped
        assert not result[0].startswith(" ")


# ---------------------------------------------------------------------------
# deduplicate_jsonl
# ---------------------------------------------------------------------------

class TestDeduplicateJsonl:
    def test_deduplicates_in_place(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        line1 = json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "v"})
        line2 = json.dumps({"p": "P2", "file": "b.py", "line": 2, "t": "c"})
        jsonl.write_text(f"{line1}\n{line1}\n{line2}\n")

        count = deduplicate_jsonl(jsonl)
        assert count == 2
        lines = jsonl.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_returns_zero_for_missing_file(self, tmp_path):
        jsonl = tmp_path / "nonexistent.jsonl"
        assert deduplicate_jsonl(jsonl) == 0

    def test_handles_empty_file(self, tmp_path):
        jsonl = tmp_path / "empty.jsonl"
        jsonl.write_text("")
        count = deduplicate_jsonl(jsonl)
        assert count == 0


# ---------------------------------------------------------------------------
# merge_jsonl
# ---------------------------------------------------------------------------

class TestMergeJsonl:
    def test_merges_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.jsonl"
        f2 = tmp_path / "b.jsonl"
        output = tmp_path / "merged.jsonl"

        f1.write_text(json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "v"}) + "\n")
        f2.write_text(json.dumps({"p": "P2", "file": "b.py", "line": 2, "t": "c"}) + "\n")

        result = merge_jsonl([f1, f2], output)
        assert result == output
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_deduplicates_across_files(self, tmp_path):
        f1 = tmp_path / "a.jsonl"
        f2 = tmp_path / "b.jsonl"
        output = tmp_path / "merged.jsonl"

        line = json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "v"})
        f1.write_text(line + "\n")
        f2.write_text(line + "\n")

        merge_jsonl([f1, f2], output)
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_skips_missing_files(self, tmp_path):
        f1 = tmp_path / "exists.jsonl"
        f1.write_text(json.dumps({"p": "P1", "file": "a.py", "line": 1, "t": "v"}) + "\n")
        missing = tmp_path / "gone.jsonl"
        output = tmp_path / "merged.jsonl"

        merge_jsonl([f1, missing], output)
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_empty_inputs(self, tmp_path):
        output = tmp_path / "merged.jsonl"
        merge_jsonl([], output)
        assert output.read_text().strip() == ""
