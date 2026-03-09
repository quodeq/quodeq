"""Minimal MCP tool server: receives findings via tool calls, writes JSONL.

Protocol: JSON-RPC 2.0 over stdio, newline-delimited JSON (no Content-Length).
No external dependencies.
"""
from __future__ import annotations

import json
import os
import sys

TOOL_NAME = "report_finding"
TOOL_DESC = (
    "Report a code quality finding (violation or compliance). "
    "Call this for EVERY finding you discover, immediately after confirming it."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "p": {"type": "string", "description": "Principle name from the standards checklist"},
        "t": {"type": "string", "enum": ["violation", "compliance"], "description": "Finding type"},
        "d": {"type": "string", "description": "Dimension being evaluated"},
        "w": {"type": "string", "description": "Short description of the finding"},
        "file": {"type": "string", "description": "File path relative to repo root"},
        "line": {"type": "integer", "description": "Line number"},
        "snippet": {"type": "string", "description": "Relevant code snippet (under 200 chars)"},
        "severity": {"type": "string", "enum": ["critical", "major", "minor"], "description": "Severity level"},
        "vt": {"type": "string", "description": "Violation type identifier"},
        "reason": {"type": "string", "description": "Why this is a violation or compliance"},
        "cwe": {"type": "integer", "description": "CWE ID if applicable"},
    },
    "required": ["p", "t", "d", "w"],
}


def _read_message() -> dict | None:
    """Read one JSON-RPC message from stdin (newline-delimited)."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        return json.loads(line)
    return None


def _send(msg: dict) -> None:
    """Write one JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(req_id: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def main() -> None:
    # Accept findings path as CLI arg (preferred) or env var (fallback).
    findings_file = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FINDINGS_FILE")
    if not findings_file:
        sys.stderr.write("Usage: mcp_findings.py <findings_file>  (or set FINDINGS_FILE env)\n")
        sys.exit(1)

    counter = 0
    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        req_id = msg.get("id")

        if method == "initialize":
            # Echo back the client's protocol version for compatibility.
            client_version = msg.get("params", {}).get("protocolVersion", "2024-11-05")
            _send(_ok(req_id, {
                "protocolVersion": client_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "quodeq-findings", "version": "1.0.0"},
            }))
        elif method in ("notifications/initialized", "notifications/cancelled"):
            pass
        elif method == "tools/list":
            _send(_ok(req_id, {"tools": [{
                "name": TOOL_NAME,
                "description": TOOL_DESC,
                "inputSchema": TOOL_SCHEMA,
            }]}))
        elif method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name != TOOL_NAME:
                _send(_ok(req_id, {
                    "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                    "isError": True,
                }))
                continue

            finding = {k: v for k, v in args.items() if v is not None}
            with open(findings_file, "a") as f:
                f.write(json.dumps(finding) + "\n")
            counter += 1

            _send(_ok(req_id, {
                "content": [{"type": "text", "text": f"Finding #{counter} recorded."}],
            }))
        elif method == "ping":
            _send(_ok(req_id, {}))
        elif req_id is not None:
            _send({"jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()
