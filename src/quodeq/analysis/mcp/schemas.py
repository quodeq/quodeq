"""MCP tool schemas and constants for the findings server.

Defines the JSON-RPC tool names, descriptions, and input schemas
for ``report_finding`` and ``get_next_files``.
"""
from __future__ import annotations

REPORT_FINDING_NAME = "report_finding"
REPORT_FINDING_DESC = (
    "Report a code quality finding (violation or compliance). "
    "Call this for EVERY finding you discover, immediately after confirming it."
)
REPORT_FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "req": {"type": "string", "description": "Requirement ID from the standards checklist (e.g. 'M-MOD-1', 'S-CON-3'). Server auto-fills principle name and dimension from this."},
        "t": {"type": "string", "enum": ["violation", "compliance"], "description": "Finding type"},
        "file": {"type": "string", "description": "File path relative to repo root"},
        "line": {"type": "integer", "description": "Line number"},
        "end_line": {"type": "integer", "description": "Last line of the violation pattern (omit if single line)"},
        "scope": {"type": "string", "enum": ["file", "class", "module"], "description": "Set when the finding affects an entire file/class/module rather than specific lines"},
        "severity": {"type": "string", "enum": ["critical", "major", "minor"], "description": "Severity level"},
        "w": {"type": "string", "description": "Short description of the finding"},
        "reason": {"type": "string", "description": "Why this is a violation or compliance"},
        "p": {"type": "string", "description": "Sub-characteristic name — auto-filled from req if omitted"},
        "d": {"type": "string", "description": "Dimension — auto-filled from server config if omitted"},
    },
    "required": ["req", "t", "file", "line", "severity", "w", "reason"],
}

_DEFAULT_FILE_BATCH_SIZE = 5
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
