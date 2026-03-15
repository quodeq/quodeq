"""Re-export for backward compatibility — moved to quodeq.analysis.mcp.dispatch."""
from quodeq.analysis.mcp.dispatch import *  # noqa: F401,F403
from quodeq.analysis.mcp.dispatch import (  # noqa: F401
    _read_message,
    _send,
    _ok,
    _handle_initialize,
    _handle_tools_list,
    _handle_tools_call,
    _handle_unknown_method,
)
