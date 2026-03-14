"""JSON-RPC dispatch handlers for the MCP findings server.

Extracted from mcp_findings.py to keep module size under 300 lines.
Defines the JSON-RPC constants, tool schemas, and the dispatch loop.
"""
from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.engine.file_queue import FileQueue
    from quodeq.engine.mcp_findings import FindingsRouter

_JSONRPC_VERSION = "2.0"
_MCP_DEFAULT_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "quodeq-findings"
_SERVER_VERSION = "1.0.0"
_JSONRPC_METHOD_NOT_FOUND = -32601

REPORT_FINDING_NAME = "report_finding"
REPORT_FINDING_DESC = (
    "Report a code quality finding (violation or compliance). "
    "Call this for EVERY finding you discover, immediately after confirming it."
)
REPORT_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "p": {"type": "string", "description": "Sub-characteristic name (the ### heading from the checklist, e.g. 'Modularity', 'Analyzability'). NEVER a requirement ID."},
        "t": {"type": "string", "enum": ["violation", "compliance"], "description": "Finding type"},
        "d": {"type": "string", "description": "Dimension being evaluated"},
        "w": {"type": "string", "description": "Short description of the finding"},
        "file": {"type": "string", "description": "File path relative to repo root"},
        "line": {"type": "integer", "description": "Line number"},
        "snippet": {"type": "string", "description": "Relevant code snippet (under 200 chars)"},
        "severity": {"type": "string", "enum": ["critical", "major", "minor"], "description": "Severity level"},
        "vt": {"type": "string", "description": "Violation type identifier"},
        "reason": {"type": "string", "description": "Why this is a violation or compliance"},
        "req": {"type": "string", "description": "Requirement ID from the standards checklist (e.g. 'R-FT-1', 'S-CON-3')"},
    },
    "required": ["p", "t", "d", "w"],
}

GET_NEXT_FILES_NAME = "get_next_files"
GET_NEXT_FILES_DESC = (
    "Get your next batch of files to analyse from the queue. "
    "Call this to receive file paths, then Read each one and report findings. "
    "When this returns an empty list, you are done."
)
GET_NEXT_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "count": {
            "type": "integer",
            "description": "Number of files to retrieve (default 5)",
        },
    },
}


def _send(msg: dict) -> None:
    """Write one JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(req_id: object, result: dict) -> dict:
    return {"jsonrpc": _JSONRPC_VERSION, "id": req_id, "result": result}


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


def _handle_initialize(request_id: object, msg: dict) -> dict:
    """Handle the 'initialize' JSON-RPC method."""
    client_version = msg.get("params", {}).get("protocolVersion", _MCP_DEFAULT_PROTOCOL_VERSION)
    return _ok(request_id, {
        "protocolVersion": client_version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
    })


def _handle_tools_list(request_id: object, *, has_queue: bool = False) -> dict:
    """Handle the 'tools/list' JSON-RPC method."""
    tools = [{
        "name": REPORT_FINDING_NAME,
        "description": REPORT_FINDING_DESC,
        "inputSchema": REPORT_FINDING_SCHEMA,
    }]
    if has_queue:
        tools.append({
            "name": GET_NEXT_FILES_NAME,
            "description": GET_NEXT_FILES_DESC,
            "inputSchema": GET_NEXT_FILES_SCHEMA,
        })
    return _ok(request_id, {"tools": tools})


def _handle_tools_call(
    request_id: object, params: dict,
    router: FindingsRouter, queue: FileQueue | None = None,
    agent_id: str = "",
) -> dict:
    """Handle the 'tools/call' JSON-RPC method."""
    name = params.get("name")
    args = params.get("arguments", {})

    if name == REPORT_FINDING_NAME:
        message, _is_dup = router.receive(args)
        return _ok(request_id, {
            "content": [{"type": "text", "text": message}],
        })

    if name == GET_NEXT_FILES_NAME:
        if queue is None:
            return _ok(request_id, {
                "content": [{"type": "text", "text": "No file queue configured."}],
                "isError": True,
            })
        count = args.get("count", 5)
        if not isinstance(count, int) or count < 1:
            count = 5
        files = queue.take(count, agent_id=agent_id)
        if not files:
            return _ok(request_id, {
                "content": [{"type": "text", "text": "Queue empty — no more files. You are done."}],
            })
        file_list = "\n".join(files)
        return _ok(request_id, {
            "content": [{"type": "text", "text": f"{len(files)} files to analyse:\n{file_list}"}],
        })

    return _ok(request_id, {
        "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
        "isError": True,
    })


def _handle_unknown_method(req_id: object, method: str) -> None:
    """Send a JSON-RPC method-not-found error for unrecognised methods."""
    if req_id is not None:
        _send({"jsonrpc": _JSONRPC_VERSION, "id": req_id,
               "error": {"code": _JSONRPC_METHOD_NOT_FOUND, "message": f"Method not found: {method}"}})


def dispatch(
    msg: dict, router: FindingsRouter,
    queue: FileQueue | None = None, agent_id: str = "",
) -> None:
    """Route a single JSON-RPC message."""
    method = msg.get("method", "")
    req_id = msg.get("id")

    if method in ("notifications/initialized", "notifications/cancelled"):
        return
    if method == "initialize":
        _send(_handle_initialize(req_id, msg))
    elif method == "tools/list":
        _send(_handle_tools_list(req_id, has_queue=queue is not None))
    elif method == "tools/call":
        _send(_handle_tools_call(req_id, msg.get("params", {}), router, queue, agent_id))
    elif method == "ping":
        _send(_ok(req_id, {}))
    else:
        _handle_unknown_method(req_id, method)
