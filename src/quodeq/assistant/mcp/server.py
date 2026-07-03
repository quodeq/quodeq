"""Read-only stdio MCP server exposing the assistant tool registry to a CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from quodeq.assistant.guard import MAX_TOOL_RESULT_CHARS
from quodeq.assistant.mcp import _jsonrpc
from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.assistant.tools._registry import ToolRegistry
from quodeq.assistant import AssistantRepository

_PROTOCOL = "2024-11-05"
_SERVER_NAME = "quodeq-assistant"


def _tools_list(registry: ToolRegistry) -> dict:
    tools = [
        {"name": t["function"]["name"], "description": t["function"]["description"],
         "inputSchema": t["function"]["parameters"]}
        for t in registry.openai_tools()
    ]
    return {"tools": tools}


def _tools_call(registry: ToolRegistry, params: dict) -> dict:
    result = registry.dispatch(params.get("name", ""), params.get("arguments") or {})
    text = json.dumps(result, ensure_ascii=False)
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + " ...[truncated]"
    return {"content": [{"type": "text", "text": text}],
            "isError": not result.get("ok", False)}


def serve(registry: ToolRegistry, *, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> None:
    while True:
        msg = _jsonrpc.read_message(stdin)
        if msg is None:
            break
        method, req_id = msg.get("method"), msg.get("id")
        try:
            if method == "initialize":
                _jsonrpc.send(_jsonrpc.ok(req_id, {
                    "protocolVersion": _PROTOCOL, "capabilities": {"tools": {}},
                    "serverInfo": {"name": _SERVER_NAME, "version": "1"}}), stdout)
            elif method == "tools/list":
                _jsonrpc.send(_jsonrpc.ok(req_id, _tools_list(registry)), stdout)
            elif method == "tools/call":
                _jsonrpc.send(_jsonrpc.ok(req_id, _tools_call(registry, msg.get("params", {}))), stdout)
            elif method == "ping":
                _jsonrpc.send(_jsonrpc.ok(req_id, {}), stdout)
            elif method and method.startswith("notifications/"):
                continue
            else:
                _jsonrpc.send(_jsonrpc.err(req_id, -32601, f"method not found: {method}"), stdout)
        except Exception as exc:  # noqa: BLE001 - server must not die on one bad request
            stderr.write(f"assistant mcp dispatch error: {exc}\n")
            stderr.flush()
            if req_id is not None:  # notifications have no id and expect no response
                _jsonrpc.send(_jsonrpc.err(req_id, -32603, f"internal error: {exc}"), stdout)


def _build_registry_from_args(ns: argparse.Namespace) -> ToolRegistry:
    # reports_dir defaults to the evaluations root so get_overview works even
    # when the caller didn't pass --reports-dir explicitly.
    if ns.reports_dir:
        reports_dir = Path(ns.reports_dir)
    else:
        from quodeq.shared._env import get_evaluations_dir  # noqa: PLC0415
        reports_dir = Path(get_evaluations_dir())
    ctx = ToolContext(
        repository=AssistantRepository(Path(ns.db_path)),
        session_id=ns.session_id,
        run_dir=Path(ns.run_dir) if ns.run_dir else None,
        repo_root=Path(ns.repo_root) if ns.repo_root else None,
        evaluators_dir=Path(ns.evaluators_dir),
        compiled_dir=Path(ns.compiled_dir),
        dimensions_file=Path(ns.dimensions_file),
        project_id=ns.project_id or None,
        reports_dir=reports_dir,
    )
    return build_registry(ctx)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--evaluators-dir", required=True)
    parser.add_argument("--compiled-dir", required=True)
    parser.add_argument("--dimensions-file", required=True)
    parser.add_argument("--project-id", default="")
    parser.add_argument("--reports-dir", default="")
    ns = parser.parse_args(argv)
    serve(_build_registry_from_args(ns), stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    main()
