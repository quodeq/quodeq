"""JSON-RPC method handlers for the MCP findings server.

Each function handles one JSON-RPC method and returns the response dict.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from quodeq import __version__
from quodeq.analysis.mcp.jsonrpc_io import _JSONRPC_VERSION, send as _send, ok as _ok
from quodeq.analysis.mcp.schemas import (
    _DEFAULT_FILE_BATCH_SIZE,
    GET_NEXT_FILES_DESC,
    GET_NEXT_FILES_NAME,
    GET_NEXT_FILES_SCHEMA,
    MARK_FILE_DONE_DESC,
    MARK_FILE_DONE_NAME,
    MARK_FILE_DONE_SCHEMA,
    REPORT_FINDING_DESC,
    REPORT_FINDING_NAME,
    REPORT_FINDING_SCHEMA,
)

if TYPE_CHECKING:
    from quodeq.analysis.subagents.file_queue import FileQueue
    from quodeq.analysis.mcp.findings_server import FindingsRouter

_JSONRPC_METHOD_NOT_FOUND = -32601
_MCP_DEFAULT_PROTOCOL_VERSION = "2024-11-05"
_SERVER_NAME = "quodeq-findings"
_SERVER_VERSION = __version__ or "0.0.0"
_DEFAULT_MAX_FILE_BATCH_SIZE = 1000


def _max_file_batch_size() -> int:
    """Return the per-call file-batch ceiling, honouring QUODEQ_MCP_MAX_BATCH."""
    raw = os.environ.get("QUODEQ_MCP_MAX_BATCH")
    if not raw:
        return _DEFAULT_MAX_FILE_BATCH_SIZE
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_FILE_BATCH_SIZE
    return value if value > 0 else _DEFAULT_MAX_FILE_BATCH_SIZE


def handle_initialize(request_id: object, msg: dict) -> dict:
    """Handle the 'initialize' JSON-RPC method."""
    client_version = msg.get("params", {}).get("protocolVersion", _MCP_DEFAULT_PROTOCOL_VERSION)
    return _ok(request_id, {
        "protocolVersion": client_version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
    })


def handle_tools_list(request_id: object, *, has_queue: bool = False) -> dict:
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
    tools.append({
        "name": MARK_FILE_DONE_NAME,
        "description": MARK_FILE_DONE_DESC,
        "inputSchema": MARK_FILE_DONE_SCHEMA,
    })
    return _ok(request_id, {"tools": tools})


def handle_tools_call(
    request_id: object, params: dict,
    router: FindingsRouter, queue: FileQueue | None = None,
    agent_id: str = "",
) -> dict:
    """Handle the 'tools/call' JSON-RPC method."""
    name = params.get("name")
    args = params.get("arguments") or {}

    if name == REPORT_FINDING_NAME:
        message, _is_dup = router.receive(args)
        return _ok(request_id, {
            "content": [{"type": "text", "text": message}],
        })

    if name == GET_NEXT_FILES_NAME:
        if queue is None:
            return _ok(request_id, {
                "content": [{"type": "text", "text": "No file queue configured. Ensure the evaluation was started with a file manifest and the queue path is set."}],
                "isError": True,
            })
        count = args.get("count", _DEFAULT_FILE_BATCH_SIZE)
        if not isinstance(count, int) or count < 1:
            count = _DEFAULT_FILE_BATCH_SIZE
        count = min(count, _max_file_batch_size())
        files = queue.take(count, agent_id=agent_id)
        if not files:
            return _ok(request_id, {
                "content": [{"type": "text", "text": "DONE. Queue empty — no more files to analyse. Stop immediately and do not call any more tools."}],
            })
        file_list = "\n".join(files)
        return _ok(request_id, {
            "content": [{"type": "text", "text": f"{len(files)} files to analyse:\n{file_list}"}],
        })

    if name == MARK_FILE_DONE_NAME:
        file = args.get("file")
        status = args.get("status")
        reason = args.get("reason") or None
        if not isinstance(file, str) or not isinstance(status, str):
            return _ok(request_id, {
                "content": [{"type": "text", "text": "mark_file_done requires 'file' (string) and 'status' (\"ok\"|\"error\")"}],
                "isError": True,
            })
        try:
            router.mark_file_done(file=file, status=status, reason=reason)
        except ValueError as exc:
            return _ok(request_id, {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            })
        return _ok(request_id, {
            "content": [{"type": "text", "text": "marked"}],
        })

    return _ok(request_id, {
        "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
        "isError": True,
    })


def handle_unknown_method(req_id: object, method: str) -> None:
    """Send a JSON-RPC method-not-found error for unrecognised methods."""
    if req_id is not None:
        _send({"jsonrpc": _JSONRPC_VERSION, "id": req_id,
               "error": {"code": _JSONRPC_METHOD_NOT_FOUND, "message": f"Method not found: {method}"}})
