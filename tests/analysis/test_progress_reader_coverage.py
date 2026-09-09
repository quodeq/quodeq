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

    def test_jsonl_line_split_across_chunk_boundary_counted_once(self, tmp_path):
        base = json.dumps({"t": "violation", "pad": ""})
        target_len = (1 << 16) + 4096  # straddles the 64 KiB read chunk
        pad = "a" * (target_len - len(base))
        line = json.dumps({"t": "violation", "pad": pad})
        assert len(line) == target_len
        reader = self._make_reader(tmp_path, jsonl_content=line + "\n")
        progress = reader.read_progress()
        assert progress["evidence"] == 1
        assert progress["violations"] == 1

    def test_stream_offset_advances_despite_processing_error(self, tmp_path, monkeypatch):
        from quodeq.analysis.stream import progress_reader as pr_module
        stream_file = tmp_path / "stream.jsonl"
        event = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
            ]}
        }
        content = json.dumps(event) + "\n"
        stream_file.write_bytes(content.encode("utf-8"))  # bytes: text mode writes CRLF on Windows
        reader = pr_module._IncrementalProgressReader(stream_file, None)

        original_parse = pr_module.parse_stream_event
        calls = {"count": 0}

        def boom(line):
            calls["count"] += 1
            raise ValueError("boom")

        monkeypatch.setattr(pr_module, "parse_stream_event", boom)

        # Processing raises, but the offset must still advance past the bytes
        # already consumed, so the next read never re-processes them.
        reader.read_progress()
        assert reader._stream_offset == len(content.encode("utf-8"))
        assert calls["count"] == 1

        monkeypatch.setattr(pr_module, "parse_stream_event", original_parse)
        progress = reader.read_progress()
        assert progress["files_read"] == 0

    def test_stream_multichunk_error_loses_only_first_chunk(self, tmp_path, monkeypatch):
        from quodeq.analysis.stream import progress_reader as pr_module

        def event_line(file_path):
            event = {
                "type": "assistant",
                "message": {"content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": file_path}},
                ]},
            }
            return json.dumps(event)

        filler_block = (event_line("/filler.py") + "\n") * 800
        sentinel_line = event_line("/tail_sentinel.py") + "\n"
        content = filler_block + sentinel_line
        filler_bytes = len(filler_block.encode("utf-8"))
        total_bytes = len(content.encode("utf-8"))
        assert filler_bytes > (1 << 16), "filler block must span the whole first chunk"
        assert total_bytes < 2 * (1 << 16), "keep this a two-chunk backlog"

        stream_file = tmp_path / "stream.jsonl"
        stream_file.write_bytes(content.encode("utf-8"))  # bytes: text mode writes CRLF on Windows
        reader = pr_module._IncrementalProgressReader(stream_file, None)

        original_parse = pr_module.parse_stream_event
        calls = {"count": 0}

        def boom(line):
            calls["count"] += 1
            raise ValueError("boom")

        monkeypatch.setattr(pr_module, "parse_stream_event", boom)

        # Raises on the very first filler line, well inside the first chunk.
        reader.read_progress()
        assert reader._stream_offset == 1 << 16
        assert calls["count"] == 1

        monkeypatch.setattr(pr_module, "parse_stream_event", original_parse)
        reader.read_progress()
        # The second chunk was never eagerly consumed by the error, so a
        # follow-up read still finds and processes the sentinel line in it.
        assert "/tail_sentinel.py" in reader._seen_files
