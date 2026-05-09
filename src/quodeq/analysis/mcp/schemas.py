"""MCP tool schemas and constants for the findings server.

Defines the JSON-RPC tool names, descriptions, and input schemas
for ``report_finding``, ``get_next_files``, and ``mark_file_done``.
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

MARK_FILE_DONE_NAME = "mark_file_done"
MARK_FILE_DONE_DESC = (
    "Call this exactly once after you have finished analysing a file, "
    "successfully or not. Pass status='ok' if you analysed the file end-to-end "
    "(even if there were no findings). Pass status='error' if you abandoned the file "
    "(token limit, parse error, retry budget exhausted). The server uses this to "
    "decide which files are safe to cache as 'done'; without it the file will be "
    "re-analysed on the next run."
)
MARK_FILE_DONE_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string", "description": "Repo-relative file path that was just analysed"},
        "status": {"type": "string", "enum": ["ok", "error"], "description": "ok if analysis completed, error if abandoned"},
        "reason": {"type": "string", "description": "Short stable code when status=error: token_limit | parse_error | retry_exhausted | subprocess_error | timeout"},
    },
    "required": ["file", "status"],
}
