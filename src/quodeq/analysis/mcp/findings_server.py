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
from quodeq.core.standards.refs import load_compiled_refs as _load_compiled_refs
from quodeq.context.precedent import load_precedent_fingerprints
from quodeq.context.project_shape import detect_shape
from quodeq.core.standards.refs import load_compiled_requirements as _load_compiled_requirements

# Re-export public API so existing imports keep working.
from quodeq.analysis.mcp.enricher import CompiledContext, FileReader  # noqa: F401
from quodeq.analysis.mcp.router import DeduplicationStore, FindingsRouter  # noqa: F401


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
            router = _build_router(findings_fh, Path(sa.findings_file), ctx, sa)
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


def _build_router(
    findings_fh, findings_path: Path, ctx: CompiledContext,
    server_args: ServerArgs,
) -> FindingsRouter:
    """Construct a FindingsRouter wired to the event log and (when configured)
    the per-file synchronous cache writer.

    The findings_path is `<run_dir>/evidence/<dim>_evidence.jsonl`, so the run
    directory is its grandparent and the project directory its great-grandparent.
    The event log lives at `<run_dir>/events.jsonl`.

    When ``server_args.dimension`` is set, the cache writer becomes mandatory:
    a findings_server scoped to a dimension MUST have ``--cache-root`` and
    ``--model-id`` so each ok marker writes the cache entry synchronously.
    Silent degradation to watcher-only is the failure mode the Phase 1 audit
    warned against -- argparse-level enforcement comes in Task 7; this check
    is defense-in-depth.
    """
    run_dir = Path(findings_path).parent.parent
    project_dir = run_dir.parent
    ctx.precedent_fingerprints = load_precedent_fingerprints(project_dir)
    from quodeq.core.events.writer import EventLogWriter  # noqa: PLC0415
    event_log = EventLogWriter(run_dir / "events.jsonl")

    cache_writer = None
    if server_args.dimension:
        if not server_args.cache_root or not server_args.model_id:
            raise RuntimeError(
                "findings_server requires --cache-root and --model-id when "
                "--dimension is set; got cache_root=%r, model_id=%r"
                % (server_args.cache_root, server_args.model_id),
            )
        from quodeq.analysis.cache.cache_writer import build_cache_writer  # noqa: PLC0415
        src_root = Path(server_args.work_dir) if server_args.work_dir else Path.cwd()
        standards_dir = Path(server_args.compiled_dir) if server_args.compiled_dir else None
        cache_writer = build_cache_writer(
            cache_root=Path(server_args.cache_root),
            src_root=src_root,
            standards_dir=standards_dir,
            dimension=server_args.dimension,
            model_id=server_args.model_id,
            language=getattr(ctx, "language", None) or "",
        )

    return FindingsRouter(
        findings_fh, context=ctx, event_log=event_log,
        on_file_done=cache_writer,
    )


if __name__ == "__main__":
    main()
