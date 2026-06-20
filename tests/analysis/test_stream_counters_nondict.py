"""#380 — extract_files_from_event / count_files_in_stream must not raise on non-dict JSON lines."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.stream.counters import count_files_in_stream, extract_files_from_event


class TestExtractFilesFromEventNonDict:
    """extract_files_from_event must tolerate any non-dict value without raising."""

    @pytest.mark.parametrize("value", [42, "foo", [1, 2, 3], True, None])
    def test_non_dict_returns_empty_set(self, value) -> None:
        assert extract_files_from_event(value) == set()

    def test_dict_still_extracts_files(self) -> None:
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/b.py"}},
                ]
            },
        }
        assert extract_files_from_event(event) == {"/a/b.py"}


class TestCountFilesInStreamNonDict:
    """count_files_in_stream must skip non-dict JSON lines and count correctly."""

    def test_non_dict_lines_are_skipped(self, tmp_path: Path) -> None:
        stream = tmp_path / "stream.json"
        lines = [
            json.dumps(42),
            json.dumps("hello"),
            json.dumps([1, 2, 3]),
            json.dumps(True),
            # A valid assistant event that reads one file
            json.dumps({
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/x/y.py"}},
                    ]
                },
            }),
        ]
        stream.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = count_files_in_stream(stream)
        assert result == {"/x/y.py"}

    def test_all_non_dict_returns_empty(self, tmp_path: Path) -> None:
        stream = tmp_path / "stream.json"
        stream.write_text(json.dumps(99) + "\n" + json.dumps([]) + "\n", encoding="utf-8")
        result = count_files_in_stream(stream)
        assert result == set()
