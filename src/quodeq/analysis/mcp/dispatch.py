"""JSON-RPC dispatch for the MCP findings server.

Thin entry point that routes messages to handlers.
Re-exports public API for backward compatibility.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from quodeq.analysis.mcp.jsonrpc_io import ok as _ok, send as _send, read_message
from quodeq.analysis.mcp.handlers import (
    handle_initialize,
    handle_tools_list,
    handle_tools_call,
    handle_unknown_method,
)

# Re-export public names so ``from dispatch import X`` keeps working.
from quodeq.analysis.mcp.schemas import (  # noqa: F401
    GET_NEXT_FILES_DESC,
    GET_NEXT_FILES_NAME,
    GET_NEXT_FILES_SCHEMA,
    REPORT_FINDING_DESC,
    REPORT_FINDING_NAME,
    REPORT_FINDING_SCHEMA,
)

if TYPE_CHECKING:
    from quodeq.analysis.subagents.file_queue import FileQueue
    from quodeq.analysis.mcp.findings_server import FindingsRouter

__all__ = [
    "REPORT_FINDING_NAME", "REPORT_FINDING_DESC", "REPORT_FINDING_SCHEMA",
    "GET_NEXT_FILES_NAME", "GET_NEXT_FILES_DESC", "GET_NEXT_FILES_SCHEMA",
    "dispatch", "read_message",
]


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
        _send(handle_initialize(req_id, msg))
    elif method == "tools/list":
        _send(handle_tools_list(req_id, has_queue=queue is not None))
    elif method == "tools/call":
        _send(handle_tools_call(req_id, msg.get("params", {}), router, queue, agent_id))
    elif method == "ping":
        _send(_ok(req_id, {}))
    else:
        handle_unknown_method(req_id, method)
