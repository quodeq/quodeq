"""Minimal MCP tool server: receives findings via tool calls, writes JSONL.

Protocol: JSON-RPC 2.0 over stdio, newline-delimited JSON (no Content-Length).
No external dependencies.
"""
from __future__ import annotations

import json
import sys
from typing import TextIO

_JSONRPC_VERSION = "2.0"
_MCP_DEFAULT_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "quodeq-findings"
_SERVER_VERSION = "1.0.0"
_JSONRPC_METHOD_NOT_FOUND = -32601

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
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write(f"Skipping malformed JSON: {line[:200]}\n")
            continue
    return None


def _send(msg: dict) -> None:
    """Write one JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(req_id: object, result: dict) -> dict:
    return {"jsonrpc": _JSONRPC_VERSION, "id": req_id, "result": result}


def _handle_initialize(request_id: object, msg: dict) -> dict:
    """Handle the 'initialize' JSON-RPC method."""
    client_version = msg.get("params", {}).get("protocolVersion", _MCP_DEFAULT_PROTOCOL_VERSION)
    return _ok(request_id, {
        "protocolVersion": client_version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
    })


def _handle_tools_list(request_id: object) -> dict:
    """Handle the 'tools/list' JSON-RPC method."""
    return _ok(request_id, {"tools": [{
        "name": TOOL_NAME,
        "description": TOOL_DESC,
        "inputSchema": TOOL_SCHEMA,
    }]})


def _handle_tools_call(request_id: object, params: dict, findings_fh: TextIO, counter: int) -> tuple[dict, int]:
    """Handle the 'tools/call' JSON-RPC method.

    Returns (response_dict, updated_counter).
    """
    name = params.get("name")
    args = params.get("arguments", {})

    if name != TOOL_NAME:
        return _ok(request_id, {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }), counter

    finding = {k: v for k, v in args.items() if v is not None}
    findings_fh.write(json.dumps(finding) + "\n")
    findings_fh.flush()
    counter += 1

    return _ok(request_id, {
        "content": [{"type": "text", "text": f"Finding #{counter} recorded."}],
    }), counter


def _handle_unknown_method(req_id: object, method: str) -> None:
    """Send a JSON-RPC method-not-found error for unrecognised methods."""
    if req_id is not None:
        _send({"jsonrpc": _JSONRPC_VERSION, "id": req_id,
               "error": {"code": _JSONRPC_METHOD_NOT_FOUND, "message": f"Method not found: {method}"}})


def _dispatch(msg: dict, findings_fh: TextIO, counter: int) -> int:
    """Route a single JSON-RPC message and return the updated counter."""
    method = msg.get("method", "")
    req_id = msg.get("id")

    if method in ("notifications/initialized", "notifications/cancelled"):
        return counter
    if method == "initialize":
        _send(_handle_initialize(req_id, msg))
    elif method == "tools/list":
        _send(_handle_tools_list(req_id))
    elif method == "tools/call":
        response, counter = _handle_tools_call(req_id, msg.get("params", {}), findings_fh, counter)
        _send(response)
    elif method == "ping":
        _send(_ok(req_id, {}))
    else:
        _handle_unknown_method(req_id, method)
    return counter


def main() -> None:
    """Run the MCP findings server, reading JSON-RPC from stdin and writing JSONL to a file."""
    from quodeq.shared.utils import get_findings_file
    findings_file = sys.argv[1] if len(sys.argv) > 1 else get_findings_file()
    if not findings_file:
        sys.stderr.write("Usage: mcp_findings.py <findings_file>  (or set FINDINGS_FILE env)\n")
        sys.exit(1)

    counter = 0
    with open(findings_file, "a") as findings_fh:
        while True:
            msg = _read_message()
            if msg is None:
                break
            counter = _dispatch(msg, findings_fh, counter)


if __name__ == "__main__":
    main()
