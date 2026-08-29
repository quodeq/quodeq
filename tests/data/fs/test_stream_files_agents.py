"""Agent-stream activity counting and JSONL appends (stream_files adapters)."""
from __future__ import annotations

import json
import time

from quodeq.data.fs.stream_files import append_jsonl_rows, count_active_agent_streams


class TestCountActiveAgentStreams:
    def test_zero_when_dir_absent(self, tmp_path):
        assert count_active_agent_streams(tmp_path / "missing", "d", window_s=30) == 0

    def test_counts_recent_streams_for_the_dim_only(self, tmp_path):
        (tmp_path / "security_agent-1.stream").write_text("x")
        (tmp_path / "security_agent-2.stream").write_text("x")
        (tmp_path / "other_agent-1.stream").write_text("x")
        (tmp_path / "security_evidence.jsonl").write_text("x")
        assert count_active_agent_streams(tmp_path, "security", window_s=30) == 2

    def test_streams_older_than_window_are_inactive(self, tmp_path):
        p = tmp_path / "security_agent-1.stream"
        p.write_text("x")
        # A `now` 60s past the file's mtime puts it outside the 30s window.
        later = time.time() + 60
        assert count_active_agent_streams(tmp_path, "security", window_s=30, now=later) == 0


class TestAppendJsonlRows:
    def test_appends_one_line_per_row(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text('{"existing": 1}\n')
        append_jsonl_rows(path, [{"a": 1}, {"b": 2}])
        lines = path.read_text().splitlines()
        assert [json.loads(line) for line in lines] == [
            {"existing": 1}, {"a": 1}, {"b": 2},
        ]

    def test_unwritable_path_is_swallowed(self, tmp_path):
        # Missing parent directory -> OSError; the contract is warn-and-drop,
        # never raise (the rows already live in the caller's evidence).
        append_jsonl_rows(tmp_path / "no-dir" / "x.jsonl", [{"a": 1}])
