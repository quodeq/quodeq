"""JSON-RPC error codes shared by quodeq's two stdio MCP servers.

The findings server (analysis/mcp/) and the assistant tool server
(assistant/mcp/) both frame errors with these codes. It lives in core so
both layers can import it. ``IntEnum`` so ``json.dumps`` still emits the
plain integer.
"""
from __future__ import annotations

from enum import IntEnum


class JsonRpcErrorCode(IntEnum):
    """JSON-RPC 2.0 error codes an MCP stdio server frames responses with.

    Only the members both servers actually construct: neither has a call
    site for PARSE_ERROR (-32700), INVALID_REQUEST (-32600) or
    INVALID_PARAMS (-32602) today, and the dead-code gate (vulture) treats
    an unreferenced member as dead code, not a dynamically-reached name --
    the whitelist doctrine (tools/vulture_whitelist.py) reserves that for
    names actually reached dynamically. Add a code here when a real call
    site needs it.
    """

    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603
