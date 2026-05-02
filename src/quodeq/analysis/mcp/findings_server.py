"""MCP tool server: receives findings via tool calls, deduplicates, enriches, writes JSONL.

Protocol: JSON-RPC 2.0 over stdio, newline-delimited JSON (no Content-Length).
No external dependencies.

This module is the entry point.  Core logic lives in:
- ``router``  -- FindingsRouter and data types
- ``ref_scoring`` -- reference selection helpers
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.mcp.args import ServerArgs, parse_args
from quodeq.analysis.mcp.dispatch import read_message, dispatch as _dispatch
from quodeq.engine._ref_utils import load_compiled_refs as _load_compiled_refs
from quodeq.context.project_shape import detect_shape
from quodeq.core.standards.refs import load_compiled_requirements as _load_compiled_requirements
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

# Re-export public API so existing imports keep working.
from quodeq.analysis.mcp.router import (  # noqa: F401
    CompiledContext,
    DeduplicationStore,
    FileReader,
    FindingsRouter,
)


def _build_compiled_context(sa: ServerArgs) -> CompiledContext:
    """Build compiled-standards context from parsed server args."""
    compiled_refs = _load_compiled_refs(sa.compiled_dir, sa.dimension)
    compiled_reqs = _load_compiled_requirements(sa.compiled_dir, sa.dimension)

    req_to_dim: dict[str, str] = {}
    if len(sa.dimensions) > 1:
        for dim in sa.dimensions:
            dim_reqs = _load_compiled_requirements(sa.compiled_dir, dim)
            for req_id in dim_reqs:
                req_to_dim[req_id] = dim

    work_dir = Path(sa.work_dir) if sa.work_dir else None
    project_shape = detect_shape(work_dir) if work_dir is not None else None

    return CompiledContext(
        compiled_refs=compiled_refs or {},
        compiled_reqs=compiled_reqs or {},
        req_to_dim=req_to_dim,
        dimension=sa.dimension,
        work_dir=work_dir,
        project_shape=project_shape,
    )


def main() -> None:
    """Run the MCP findings server, reading JSON-RPC from stdin and writing JSONL to a file."""
    sa = parse_args()
    if not sa.findings_file:
        sys.stderr.write(
            "Error: findings output path is required.\n"
            "Usage: mcp_findings.py <findings_file> [--compiled-dir DIR --dimension DIM]"
            " [--queue PATH --agent-id ID]\n"
            "Provide the path where findings JSONL should be written.\n"
        )
        sys.exit(1)

    ctx = _build_compiled_context(sa)

    queue: FileQueue | None = None
    if sa.queue_path:
        queue = FileQueue(Path(sa.queue_path))

    try:
        with open(sa.findings_file, "a") as findings_fh:
            router = _build_router(findings_fh, Path(sa.findings_file), ctx)
            while True:
                msg = read_message()
                if msg is None:
                    break
                try:
                    _dispatch(msg, router, queue, sa.agent_id)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
                    sys.stderr.write(
                        f"Dispatch error: {exc}. "
                        f"Check that the message format matches the expected MCP schema.\n"
                    )
    except OSError as exc:
        sys.stderr.write(f"Cannot open findings file {sa.findings_file}: {exc}\n")
        sys.exit(1)


def _build_router(findings_fh, findings_path: Path, ctx: CompiledContext) -> FindingsRouter:
    """Construct a FindingsRouter wired to dual-write into the run's evaluation.db.

    The findings_path is `<run_dir>/evidence/<dim>_evidence.jsonl`, so the run
    directory is its grandparent. SqliteFindingsRepository creates / opens
    `<run_dir>/evaluation.db` lazily on first insert.
    """
    run_dir = Path(findings_path).parent.parent
    repo = SqliteFindingsRepository(run_dir)
    return FindingsRouter(findings_fh, context=ctx, findings_repo=repo)


if __name__ == "__main__":
    main()
