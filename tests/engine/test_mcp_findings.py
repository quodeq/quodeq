"""Tests for the MCP findings server (JSON-RPC protocol, JSONL writing)."""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.engine import mcp_findings
from quodeq.core.standards.refs import load_compiled_refs

from tests.engine.conftest import _make_request, _run_server

_JSONRPC_METHOD_NOT_FOUND = -32601


class TestInitialize:
    def test_returns_server_info(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [_make_request("initialize", 1, {"protocolVersion": "2024-11-05"})],
            findings_file,
        )
        assert len(responses) == 1
        result = responses[0]["result"]
        assert result["serverInfo"]["name"] == "quodeq-findings"
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]

    def test_uses_client_protocol_version(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [_make_request("initialize", 1, {"protocolVersion": "2025-01-01"})],
            findings_file,
        )
        assert responses[0]["result"]["protocolVersion"] == "2025-01-01"


class TestToolsList:
    def test_lists_report_finding_tool(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [_make_request("tools/list", 2)],
            findings_file,
        )
        tools = responses[0]["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert "report_finding" in names
        assert "mark_file_done" in names
        report_tool = next(tool for tool in tools if tool["name"] == "report_finding")
        assert "inputSchema" in report_tool


class TestToolsCall:
    def test_report_finding_writes_jsonl(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        finding = {"p": "M-ANA-1", "t": "violation", "d": "maintainability", "w": "File too long"}
        responses = _run_server(
            [_make_request("tools/call", 3, {"name": "report_finding", "arguments": finding})],
            str(findings_file),
        )
        result = responses[0]["result"]
        assert "Finding #1 recorded" in result["content"][0]["text"]
        assert not result.get("isError")
        written = json.loads(findings_file.read_text().strip())
        assert written["p"] == "M-ANA-1"
        assert written["t"] == "violation"

    def test_multiple_findings_increment_counter(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        f1 = {"p": "P1", "t": "violation", "d": "security", "w": "Issue 1"}
        f2 = {"p": "P2", "t": "compliance", "d": "security", "w": "Good pattern"}
        responses = _run_server(
            [
                _make_request("tools/call", 1, {"name": "report_finding", "arguments": f1}),
                _make_request("tools/call", 2, {"name": "report_finding", "arguments": f2}),
            ],
            str(findings_file),
        )
        assert "Finding #1" in responses[0]["result"]["content"][0]["text"]
        assert "Finding #2" in responses[1]["result"]["content"][0]["text"]
        lines = findings_file.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_unknown_tool_returns_error(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [_make_request("tools/call", 4, {"name": "unknown_tool", "arguments": {}})],
            findings_file,
        )
        result = responses[0]["result"]
        assert result["isError"] is True
        assert "Unknown tool" in result["content"][0]["text"]

    def test_null_values_stripped_from_finding(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        finding = {"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "file": None}
        _run_server(
            [_make_request("tools/call", 5, {"name": "report_finding", "arguments": finding})],
            str(findings_file),
        )
        written = json.loads(findings_file.read_text().strip())
        assert "file" not in written

    def test_duplicate_finding_is_skipped(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        finding = {"p": "P1", "t": "violation", "d": "security", "w": "Issue", "file": "a.py", "line": 10}
        responses = _run_server(
            [
                _make_request("tools/call", 1, {"name": "report_finding", "arguments": finding}),
                _make_request("tools/call", 2, {"name": "report_finding", "arguments": finding}),
            ],
            str(findings_file),
        )
        assert "Finding #1" in responses[0]["result"]["content"][0]["text"]
        assert "Duplicate" in responses[1]["result"]["content"][0]["text"]
        lines = findings_file.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_same_file_line_different_type_not_duplicate(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        v = {"p": "P1", "t": "violation", "d": "security", "w": "Bad", "file": "a.py", "line": 10}
        c = {"p": "P1", "t": "compliance", "d": "security", "w": "Good", "file": "a.py", "line": 10}
        responses = _run_server(
            [
                _make_request("tools/call", 1, {"name": "report_finding", "arguments": v}),
                _make_request("tools/call", 2, {"name": "report_finding", "arguments": c}),
            ],
            str(findings_file),
        )
        assert "Finding #1" in responses[0]["result"]["content"][0]["text"]
        assert "Finding #2" in responses[1]["result"]["content"][0]["text"]
        lines = findings_file.read_text().strip().splitlines()
        assert len(lines) == 2


class TestNotifications:
    def test_notifications_are_silently_ignored(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                _make_request("tools/list", 1),
            ],
            findings_file,
        )
        assert len(responses) == 1
        assert responses[0]["id"] == 1


class TestPing:
    def test_ping_returns_empty_result(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [_make_request("ping", 10)],
            findings_file,
        )
        assert responses[0]["result"] == {}


class TestUnknownMethod:
    def test_unknown_method_returns_error(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        responses = _run_server(
            [_make_request("nonexistent/method", 99)],
            findings_file,
        )
        assert responses[0]["error"]["code"] == _JSONRPC_METHOD_NOT_FOUND


class TestLoadCompiledRefs:
    def test_loads_refs_from_compiled_json(self, tmp_path: Path) -> None:
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        data = {"principles": [{"requirements": [
            {"id": "R-FT-1", "refs": [
                {"source": "cwe", "id": "391", "url": "https://cwe.mitre.org/data/definitions/391.html"},
            ]},
            {"id": "R-FT-2", "refs": [
                {"source": "cert", "id": "ERR08-J", "url": "https://example.com/ERR08-J"},
            ]},
        ]}]}
        (compiled_dir / "reliability.json").write_text(json.dumps(data))
        result = load_compiled_refs(str(compiled_dir), "reliability")
        assert "R-FT-1" in result
        assert result["R-FT-1"][0]["label"] == "CWE-391"
        assert "R-FT-2" in result
        assert result["R-FT-2"][0]["label"] == "ERR08-J"

    def test_skips_refs_without_url(self, tmp_path: Path) -> None:
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        data = {"principles": [{"requirements": [
            {"id": "R-1", "refs": [
                {"source": "internal", "id": "M-ANA-1"},  # no url
                {"source": "cwe", "id": "123", "url": "https://cwe.mitre.org/data/definitions/123.html"},
            ]},
        ]}]}
        (compiled_dir / "maintainability.json").write_text(json.dumps(data))
        result = load_compiled_refs(str(compiled_dir), "maintainability")
        assert len(result["R-1"]) == 1
        assert result["R-1"][0]["label"] == "CWE-123"

    def test_returns_empty_for_missing_file(self, tmp_path: Path) -> None:
        result = load_compiled_refs(str(tmp_path / "missing"), "security")
        assert result == {}

    def test_returns_empty_without_args(self) -> None:
        assert load_compiled_refs(None, None) == {}


class TestMainEntryPoint:
    def test_exits_without_findings_file(self) -> None:
        with patch.object(sys, "argv", ["mcp_findings.py"]), \
             patch.dict("os.environ", {}, clear=True), \
             pytest.raises(SystemExit, match="1"):
            mcp_findings.main()

    def test_accepts_findings_file_from_env(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        stdin_text = _make_request("ping", 1) + "\n"
        stdout_buf = StringIO()
        with patch.object(sys, "stdin", StringIO(stdin_text)), \
             patch.object(sys, "stdout", stdout_buf), \
             patch.object(sys, "argv", ["mcp_findings.py"]), \
             patch.dict("os.environ", {"FINDINGS_FILE": findings_file}):
            mcp_findings.main()
        responses = [json.loads(line) for line in stdout_buf.getvalue().strip().splitlines()]
        assert responses[0]["result"] == {}
