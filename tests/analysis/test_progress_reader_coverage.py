"""Tests for quodeq.analysis.stream.progress_reader — incremental progress reader."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestIncrementalProgressReader:
    def _make_reader(self, tmp_path, stream_content="", jsonl_content=None):
        from quodeq.analysis.stream.progress_reader import _IncrementalProgressReader
        stream_file = tmp_path / "stream.jsonl"
        stream_file.write_text(stream_content)
        jsonl_file = None
        if jsonl_content is not None:
            jsonl_file = tmp_path / "evidence.jsonl"
            jsonl_file.write_text(jsonl_content)
        return _IncrementalProgressReader(stream_file, jsonl_file)

    def test_empty_files(self, tmp_path):
        reader = self._make_reader(tmp_path)
        progress = reader.read_progress()
        assert progress["files_read"] == 0
        assert progress["evidence"] == 0
        assert progress["violations"] == 0
        assert progress["compliances"] == 0

    def test_reads_stream_files(self, tmp_path):
        event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/app/main.py"}},
                    {"type": "tool_use", "name": "Grep", "input": {"path": "/app/utils.py"}},
                ]
            }
        }
        reader = self._make_reader(tmp_path, json.dumps(event) + "\n")
        progress = reader.read_progress()
        assert progress["files_read"] == 2

    def test_reads_jsonl_findings(self, tmp_path):
        jsonl = (
            json.dumps({"t": "violation"}) + "\n"
            + json.dumps({"t": "compliance"}) + "\n"
            + json.dumps({"t": "other"}) + "\n"
        )
        reader = self._make_reader(tmp_path, jsonl_content=jsonl)
        progress = reader.read_progress()
        assert progress["evidence"] == 3
        assert progress["violations"] == 1
        assert progress["compliances"] == 1

    def test_incremental_reads(self, tmp_path):
        stream_file = tmp_path / "stream.jsonl"
        stream_file.write_text("")
        from quodeq.analysis.stream.progress_reader import _IncrementalProgressReader
        reader = _IncrementalProgressReader(stream_file, None)

        # First read: empty
        p1 = reader.read_progress()
        assert p1["files_read"] == 0

        # Append data
        event = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
            ]}
        }
        stream_file.write_text(json.dumps(event) + "\n")
        p2 = reader.read_progress()
        assert p2["files_read"] == 1

    def test_jsonl_with_bad_json(self, tmp_path):
        jsonl = "not json\n" + json.dumps({"t": "violation"}) + "\n"
        reader = self._make_reader(tmp_path, jsonl_content=jsonl)
        progress = reader.read_progress()
        assert progress["evidence"] == 2  # both lines counted
        assert progress["violations"] == 1

    def test_no_jsonl_file(self, tmp_path):
        from quodeq.analysis.stream.progress_reader import _IncrementalProgressReader
        stream_file = tmp_path / "stream.jsonl"
        stream_file.write_text("")
        reader = _IncrementalProgressReader(stream_file, tmp_path / "nonexistent.jsonl")
        progress = reader.read_progress()
        assert progress["evidence"] == 0

    def test_stream_read_error(self, tmp_path):
        from quodeq.analysis.stream.progress_reader import _IncrementalProgressReader
        stream_file = tmp_path / "stream.jsonl"
        stream_file.write_text("")
        reader = _IncrementalProgressReader(stream_file, None)
        # Remove the file to trigger OSError on read
        stream_file.unlink()
        progress = reader.read_progress()
        assert progress["files_read"] == 0
