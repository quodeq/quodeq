"""JSON-RPC ``method`` values of the MCP protocol, shared by quodeq's two stdio MCP servers.

The findings server (analysis/mcp/dispatch.py) and the assistant tool server
(assistant/mcp/server.py) both route on these. It lives in core so both
layers can import it.
"""
from __future__ import annotations

from enum import StrEnum


class McpMethod(StrEnum):
    """JSON-RPC method names an MCP stdio server understands."""

    INITIALIZE = "initialize"
    NOTIFICATIONS_INITIALIZED = "notifications/initialized"
    NOTIFICATIONS_CANCELLED = "notifications/cancelled"
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    PING = "ping"


# Per-tool ``_meta`` both servers attach in ``tools/list``. Antigravity's CLI
# (agy) otherwise loads MCP tools on demand, reading each schema from a file
# under its own home that a scan's permission rules may not let it read.
# Other clients ignore unknown ``_meta`` keys, as the MCP spec allows.
TOOL_META = {"antigravity/alwaysLoad": True}
