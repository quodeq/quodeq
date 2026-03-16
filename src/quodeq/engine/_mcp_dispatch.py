"""Re-export for backward compatibility — moved to quodeq.analysis.mcp.dispatch."""
from quodeq.analysis.mcp.dispatch import (  # noqa: F401
    REPORT_FINDING_NAME,
    REPORT_FINDING_DESC,
    REPORT_FINDING_SCHEMA,
    GET_NEXT_FILES_NAME,
    GET_NEXT_FILES_DESC,
    GET_NEXT_FILES_SCHEMA,
    dispatch,
    _read_message,
    _send,
    _ok,
    _handle_initialize,
    _handle_tools_list,
    _handle_tools_call,
    _handle_unknown_method,
)
