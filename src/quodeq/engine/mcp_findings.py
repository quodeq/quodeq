"""MCP tool server: receives findings via tool calls, deduplicates, enriches, writes JSONL.

Protocol: JSON-RPC 2.0 over stdio, newline-delimited JSON (no Content-Length).
No external dependencies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from quodeq.engine.file_queue import FileQueue
from quodeq.engine._mcp_args import _ServerArgs, _parse_args

_FINDING_SCHEMA_VERSION = 1
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

# Kept for backward compatibility with imports
TOOL_NAME = REPORT_FINDING_NAME
TOOL_SCHEMA = REPORT_FINDING_SCHEMA


class FindingsRouter:
    """Deduplicates and enriches findings before writing to JSONL.

    - Dedup by (principle, file, line, type) — skips duplicate findings
    - Enriches req_refs from compiled standards — LLM doesn't need to pick refs
    - Returns feedback to the LLM so it can move on from duplicates
    """

    def __init__(self, output_fh: TextIO, compiled_refs: dict[str, list[dict]] | None = None):
        self._fh = output_fh
        self._refs = compiled_refs or {}
        self._seen: set[tuple] = set()
        self.counter = 0

    def receive(self, args: dict) -> tuple[str, bool]:
        """Process a finding. Returns (message, is_duplicate)."""
        key = (args.get("p"), args.get("file"), args.get("line"), args.get("t"))
        if key in self._seen:
            return "Duplicate finding, already captured. Move on.", True
        self._seen.add(key)

        finding: dict = {"schema_version": _FINDING_SCHEMA_VERSION}
        finding.update({k: v for k, v in args.items() if v is not None})

        # Enrich with compiled standard refs — server-side, zero LLM tokens
        req = args.get("req")
        if req and req in self._refs:
            finding["req_refs"] = self._refs[req]

        self._fh.write(json.dumps(finding) + "\n")
        self._fh.flush()
        self.counter += 1
        return f"Finding #{self.counter} recorded.", False


def _load_compiled_refs(compiled_dir: str | None, dimension: str | None) -> dict[str, list[dict]]:
    """Load {req_id: [{label, url}, ...]} from compiled standards."""
    if not compiled_dir or not dimension:
        return {}
    try:
        data = json.loads((Path(compiled_dir) / f"{dimension}.json").read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    lookup: dict[str, list[dict]] = {}
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            req_id = req.get("id")
            if not req_id:
                continue
            refs = [{"label": _ref_label(r), "url": r["url"]} for r in req.get("refs", []) if r.get("url")]
            if refs:
                lookup[req_id] = refs
    return lookup


def _ref_label(ref: dict) -> str:
    """Build a display label for a ref."""
    source = ref.get("source", "")
    ref_id = ref.get("id")
    if source == "cwe" and ref_id:
        return f"CWE-{ref_id}"
    if ref_id:
        return ref_id
    return source.upper() if source else "REF"


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


def _send(msg: dict) -> None:
    """Write one JSON-RPC message to stdout (newline-delimited)."""
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(req_id: object, result: dict) -> dict:
    return {"jsonrpc": _JSONRPC_VERSION, "id": req_id, "result": result}


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


def _dispatch(
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


def main() -> None:
    """Run the MCP findings server, reading JSON-RPC from stdin and writing JSONL to a file."""
    sa = _parse_args()
    if not sa.findings_file:
        sys.stderr.write(
            "Usage: mcp_findings.py <findings_file> [--compiled-dir DIR --dimension DIM]"
            " [--queue PATH --agent-id ID]\n"
        )
        sys.exit(1)

    compiled_refs = _load_compiled_refs(sa.compiled_dir, sa.dimension)
    queue: FileQueue | None = None
    if sa.queue_path:
        queue = FileQueue(Path(sa.queue_path))

    try:
        with open(sa.findings_file, "a") as findings_fh:
            router = FindingsRouter(findings_fh, compiled_refs)
            while True:
                msg = _read_message()
                if msg is None:
                    break
                _dispatch(msg, router, queue, sa.agent_id)
    except OSError as exc:
        sys.stderr.write(f"Cannot open findings file {sa.findings_file}: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
