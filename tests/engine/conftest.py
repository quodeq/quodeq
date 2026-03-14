"""Shared test helpers for engine tests."""
from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import patch

from quodeq.engine import mcp_findings


def _make_request(method: str, req_id: int = 1, params: dict | None = None) -> str:
    """Build a JSON-RPC request string."""
    msg: dict = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _run_server(input_lines: list[str], findings_file: str) -> list[dict]:
    """Feed *input_lines* to the MCP server and return parsed response dicts."""
    stdin_text = "\n".join(input_lines) + "\n"
    stdout_buf = StringIO()
    with patch.object(sys, "stdin", StringIO(stdin_text)), \
         patch.object(sys, "stdout", stdout_buf), \
         patch.object(sys, "argv", ["mcp_findings.py", findings_file]):
        mcp_findings.main()
    output = stdout_buf.getvalue().strip()
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def _evidence_line(**overrides) -> str:
    """Build a JSONL evidence line with sensible defaults."""
    obj = {
        "p": "ts-001",
        "t": "violation",
        "d": "security",
        "w": "eval usage",
        "file": "src/app.ts",
        "line": 10,
        "snippet": "eval(userInput)",
        "severity": "high",
        "vt": "code-injection",
        "reason": "eval is dangerous",
    }
    obj.update(overrides)
    return json.dumps(obj)
