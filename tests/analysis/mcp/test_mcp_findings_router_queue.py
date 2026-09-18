"""Tests for the get_next_files MCP tool and findings_server argument parsing."""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.mcp import findings_server as mcp_findings
from quodeq.analysis.mcp.args import parse_args

from tests._analysis_helpers import _make_request, _run_server


def _run_server_with_queue(
    input_lines: list[str], findings_file: str,
    queue_path: str, agent_id: str = "test-agent",
) -> list[dict]:
    """Run the MCP server with --queue and --agent-id flags."""
    stdin_text = "\n".join(input_lines) + "\n"
    stdout_buf = StringIO()
    argv = [
        "mcp_findings.py", findings_file,
        "--queue", queue_path,
        "--agent-id", agent_id,
    ]
    with patch.object(sys, "stdin", StringIO(stdin_text)), \
         patch.object(sys, "stdout", stdout_buf), \
         patch.object(sys, "argv", argv):
        mcp_findings.main()
    output = stdout_buf.getvalue().strip()
    return [json.loads(line) for line in output.splitlines() if line.strip()]


class TestGetNextFiles:
    def test_tools_list_includes_get_next_files(self, tmp_path: Path) -> None:
        from quodeq.analysis.subagents.file_queue import FileQueue
        qp = tmp_path / "queue.json"
        FileQueue(qp, ["a.py", "b.py"])
        responses = _run_server_with_queue(
            [_make_request("tools/list", 1)],
            str(tmp_path / "findings.jsonl"),
            str(qp),
        )
        tools = responses[0]["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "report_finding" in names
        assert "get_next_files" in names

    def test_tools_list_without_queue_has_no_get_next_files(self, tmp_path: Path) -> None:
        responses = _run_server(
            [_make_request("tools/list", 1)],
            str(tmp_path / "findings.jsonl"),
        )
        tools = responses[0]["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "report_finding" in names
        assert "get_next_files" not in names

    def test_get_next_files_returns_batch(self, tmp_path: Path) -> None:
        from quodeq.analysis.subagents.file_queue import FileQueue
        files = ["src/a.py", "src/b.py", "src/c.py"]
        qp = tmp_path / "queue.json"
        FileQueue(qp, files)
        responses = _run_server_with_queue(
            [_make_request("tools/call", 1, {"name": "get_next_files", "arguments": {"count": 2}})],
            str(tmp_path / "findings.jsonl"),
            str(qp),
        )
        text = responses[0]["result"]["content"][0]["text"]
        assert "2 files" in text
        assert "src/a.py" in text
        assert "src/b.py" in text

    def test_get_next_files_drains_queue(self, tmp_path: Path) -> None:
        from quodeq.analysis.subagents.file_queue import FileQueue
        qp = tmp_path / "queue.json"
        FileQueue(qp, ["a.py", "b.py"])
        responses = _run_server_with_queue(
            [
                _make_request("tools/call", 1, {"name": "get_next_files", "arguments": {"count": 10}}),
                _make_request("tools/call", 2, {"name": "get_next_files", "arguments": {}}),
            ],
            str(tmp_path / "findings.jsonl"),
            str(qp),
        )
        assert "2 files" in responses[0]["result"]["content"][0]["text"]
        assert "done" in responses[1]["result"]["content"][0]["text"].lower()

    def test_get_next_files_records_agent_id(self, tmp_path: Path) -> None:
        from quodeq.analysis.subagents.file_queue import FileQueue
        qp = tmp_path / "queue.json"
        FileQueue(qp, ["a.py"])
        _run_server_with_queue(
            [_make_request("tools/call", 1, {"name": "get_next_files", "arguments": {}})],
            str(tmp_path / "findings.jsonl"),
            str(qp),
            agent_id="agent-42",
        )
        q = FileQueue(qp)
        log = q.taken_log()
        assert len(log) == 1
        assert log[0]["agent"] == "agent-42"

    def test_get_next_files_without_queue_returns_error(self, tmp_path: Path) -> None:
        responses = _run_server(
            [_make_request("tools/call", 1, {"name": "get_next_files", "arguments": {}})],
            str(tmp_path / "findings.jsonl"),
        )
        result = responses[0]["result"]
        assert result["isError"] is True
        assert "No file queue" in result["content"][0]["text"]


class TestParseArgs:
    def test_work_dir_flag(self) -> None:
        sa = parse_args(["findings.jsonl", "--work-dir", "/tmp/repo"])
        assert sa.work_dir == "/tmp/repo"

    def test_work_dir_default_none(self) -> None:
        sa = parse_args(["findings.jsonl"])
        assert sa.work_dir is None
