"""Tests for the low-level JSON-RPC line reader: malformed and non-object lines."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

from tests._analysis_helpers import _make_request, _run_server


class TestReadMessageSkipsNonObjectLines:
    def test_null_list_and_string_are_skipped_then_valid_request_served(
        self, tmp_path: Path,
    ) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        stdin_lines = [
            "null",
            "[1]",
            '"x"',
            _make_request("initialize", 1, {"protocolVersion": "2024-11-05"}),
        ]
        responses = _run_server(stdin_lines, findings_file)
        assert len(responses) == 1
        assert responses[0]["result"]["serverInfo"]["name"] == "quodeq-findings"


class TestDispatchNonDictParams:
    def test_tools_call_with_null_params_gets_a_response(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        stdin_lines = [
            '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":null}',
            _make_request("ping", 3),
        ]
        responses = _run_server(stdin_lines, findings_file)
        assert len(responses) == 2
        assert responses[0]["id"] == 1
        assert "result" in responses[0] or "error" in responses[0]
        assert responses[1]["result"] == {}

    def test_initialize_with_string_params_gets_a_response(self, tmp_path: Path) -> None:
        findings_file = str(tmp_path / "findings.jsonl")
        stdin_lines = [
            '{"jsonrpc":"2.0","id":2,"method":"initialize","params":"x"}',
            _make_request("ping", 4),
        ]
        responses = _run_server(stdin_lines, findings_file)
        assert len(responses) == 2
        assert responses[0]["id"] == 2
        assert "result" in responses[0] or "error" in responses[0]
        assert responses[1]["result"] == {}


class TestReadMessageUnit:
    def test_skips_non_dict_then_returns_dict(self) -> None:
        from quodeq.analysis.mcp.jsonrpc_io import read_message

        with patch.object(sys, "stdin", io.StringIO('[1]\n{"id": 1}\n')):
            assert read_message() == {"id": 1}
