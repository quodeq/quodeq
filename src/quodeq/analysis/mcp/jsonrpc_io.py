"""Low-level JSON-RPC I/O helpers for the MCP findings server.

Handles reading/writing newline-delimited JSON-RPC messages over stdio.
"""
from __future__ import annotations

import json
import sys

_JSONRPC_VERSION = "2.0"
_MAX_LOG_LINE_PREVIEW = 200


def send(msg: dict) -> None:
    """Write one JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def ok(req_id: object, result: dict) -> dict:
    """Build a successful JSON-RPC response."""
    return {"jsonrpc": _JSONRPC_VERSION, "id": req_id, "result": result}


def read_message() -> dict | None:
    """Read one JSON-RPC message from stdin (newline-delimited)."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write(f"Skipping malformed JSON: {line[:_MAX_LOG_LINE_PREVIEW]}\n")
            continue
    return None
