"""Tests for FindingsRouter and get_next_files (split from test_mcp_findings)."""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.engine import mcp_findings

from tests.engine.conftest import _make_request, _run_server


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


class TestFindingsRouter:
    def test_enriches_req_refs_from_compiled(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        compiled_refs = {
            "S-CON-1": [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}],
        }
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, compiled_refs)
            msg, dup = router.receive({"p": "Confidentiality", "t": "violation", "d": "security", "w": "Hardcoded key", "req": "S-CON-1"})
        assert not dup
        assert "Finding #1" in msg
        written = json.loads(findings_file.read_text().strip())
        assert written["req_refs"] == [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}]

    def test_no_enrichment_without_matching_req(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        compiled_refs = {"S-CON-1": [{"label": "CWE-798", "url": "https://example.com"}]}
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, compiled_refs)
            router.receive({"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "req": "UNKNOWN-1"})
        written = json.loads(findings_file.read_text().strip())
        assert "req_refs" not in written

    def test_no_enrichment_without_compiled_refs(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "req": "S-CON-1"})
        written = json.loads(findings_file.read_text().strip())
        assert "req_refs" not in written


class TestGetNextFiles:
    def test_tools_list_includes_get_next_files(self, tmp_path: Path) -> None:
        from quodeq.engine.file_queue import FileQueue
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
        from quodeq.engine.file_queue import FileQueue
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
        from quodeq.engine.file_queue import FileQueue
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
        from quodeq.engine.file_queue import FileQueue
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
