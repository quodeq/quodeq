"""MCP tool server: receives findings via tool calls, deduplicates, enriches, writes JSONL.

Protocol: JSON-RPC 2.0 over stdio, newline-delimited JSON (no Content-Length).
No external dependencies.

This module is the entry point. Core logic lives in:
- ``args`` -- the command line the pipeline spawns the server with
- ``dispatch`` -- JSON-RPC message loop and method table
- ``router`` -- FindingsRouter and data types
- ``enricher`` -- standards lookup, code snippets, precedent and severity gates
- ``ref_scoring`` -- reference selection helpers
"""
from __future__ import annotations

import sys
from pathlib import Path

from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.mcp.args import ServerArgs, parse_args
from quodeq.analysis.mcp.dispatch import read_message, dispatch as _dispatch
from quodeq.analysis.mcp.jsonrpc_io import JSONRPC_VERSION, send as _send
from quodeq.data.fs.standards_loader import load_compiled_refs as _load_compiled_refs
from quodeq.context.precedent import load_precedent_corpus, load_precedent_fingerprints
from quodeq.config.context_env import precedent_settings
from quodeq.services.precedent_dismiss import precedent_match_hook
from quodeq.context.project_shape import detect_shape
from quodeq.context.trust_model import resolve_trust_model
from quodeq.data.fs.standards_loader import load_compiled_requirements as _load_compiled_requirements
from quodeq.data.fs.standards_prefs import load_project_overrides
from quodeq.data.sqlite.findings_queries import (
    dismissed_source_stamp,
    read_dismissed_snippets_strict,
)
from quodeq.shared.fault_isolation import run_isolated

# Re-export public API so existing imports keep working.
from quodeq.analysis.mcp.enricher import CompiledContext, FileReader  # noqa: F401
from quodeq.analysis.mcp.router import DeduplicationStore, FindingsRouter  # noqa: F401

# JSON-RPC 2.0 reserved server-error code for "something went wrong handling
# this request that isn't a malformed request or an unknown method" -- see
# handlers.py's _JSONRPC_METHOD_NOT_FOUND for the sibling constant.
_JSONRPC_INTERNAL_ERROR = -32603


class _StderrWarn:
    """Minimal ``Warns`` adapter (see ``shared.fault_isolation``) that writes
    to stderr. This subprocess has no LogSink/logging wiring of its own --
    stderr is its one diagnostic channel, same as every other error path in
    this module."""

    def warning(self, message: str) -> None:
        """Write *message* to stderr, matching this module's other stderr writes."""
        sys.stderr.write(message + "\n")


_STDERR_WARN = _StderrWarn()


def _send_dispatch_error_response(msg: dict, exc: Exception) -> None:
    """JSON-RPC error response for a message whose handling failed
    unexpectedly (any exception ``_dispatch`` doesn't itself recognize).

    Mirrors ``handlers.handle_unknown_method``'s request-id gating: a
    notification (no ``id``) gets no response, per the JSON-RPC 2.0 spec.
    The failure itself is already logged, with its traceback, by
    ``run_isolated`` at the call site.
    """
    req_id = msg.get("id")
    if req_id is not None:
        _send({
            "jsonrpc": JSONRPC_VERSION, "id": req_id,
            "error": {
                "code": _JSONRPC_INTERNAL_ERROR,
                "message": f"{type(exc).__name__}: {exc}",
            },
        })


def _build_compiled_context(sa: ServerArgs) -> CompiledContext:
    """Build compiled-standards context from parsed server args."""
    work_dir = Path(sa.work_dir) if sa.work_dir else None
    overrides = load_project_overrides(work_dir)

    compiled_refs = _load_compiled_refs(sa.compiled_dir, sa.dimension)
    compiled_reqs = _load_compiled_requirements(sa.compiled_dir, sa.dimension, overrides=overrides)

    req_to_dim: dict[str, str] = {}
    if len(sa.dimensions) > 1:
        for dim in sa.dimensions:
            dim_reqs = _load_compiled_requirements(sa.compiled_dir, dim)
            for req_id in dim_reqs:
                req_to_dim[req_id] = dim

    project_shape = detect_shape(work_dir) if work_dir is not None else None
    trust_model = resolve_trust_model(work_dir) if work_dir is not None else None

    return CompiledContext(
        compiled_refs=compiled_refs or {},
        compiled_reqs=compiled_reqs or {},
        req_to_dim=req_to_dim,
        dimension=sa.dimension,
        work_dir=work_dir,
        project_shape=project_shape,
        trust_model=trust_model,
    )


def main() -> None:
    """Run the MCP findings server, reading JSON-RPC from stdin and writing JSONL to a file."""
    sa = parse_args()
    if not sa.findings_file:
        sys.stderr.write(
            "Error: findings output path is required.\n"
            "Usage: python -m quodeq.analysis.mcp.findings_server <findings_file>"
            " [--compiled-dir DIR --dimension DIM]"
            " [--queue PATH --agent-id ID]\n"
            "Provide the path where findings JSONL should be written.\n"
        )
        sys.exit(1)

    ctx = _build_compiled_context(sa)

    queue: FileQueue | None = None
    if sa.queue_path:
        queue = FileQueue(Path(sa.queue_path))

    try:
        with open(sa.findings_file, "a", encoding="utf-8") as findings_fh:
            router = _build_router(findings_fh, Path(sa.findings_file), ctx, sa)
            while True:
                msg = read_message()
                if msg is None:
                    break
                run_isolated(
                    lambda msg=msg: _dispatch(msg, router, queue, sa.agent_id),
                    label=f"MCP message dispatch ({msg.get('method', '?')!r})",
                    log=_STDERR_WARN,
                    on_error=lambda exc, msg=msg: _send_dispatch_error_response(msg, exc),
                )
    except OSError as exc:
        sys.stderr.write(f"Cannot open findings file {sa.findings_file}: {exc}\n")
        sys.exit(1)
    except RuntimeError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        sys.exit(1)


def _resolve_dimension_cache_writer(server_args: ServerArgs):
    """Build the per-file synchronous cache writer, or None when undimensioned.

    When ``server_args.dimension`` is set, the cache writer becomes mandatory:
    a findings_server scoped to a dimension MUST have ``--cache-root`` and
    ``--model-id`` so each ok marker writes the cache entry synchronously.
    Degrading silently to watcher-only is the dangerous failure: the run
    looks healthy while every dimension it scoped comes back cold on the
    next scan. argparse cannot express the dependency, so the check lives
    here.
    """
    if not server_args.dimension:
        return None
    if not server_args.cache_root or not server_args.model_id:
        raise RuntimeError(
            "findings_server requires --cache-root and --model-id when "
            "--dimension is set; got cache_root=%r, model_id=%r"
            % (server_args.cache_root, server_args.model_id),
        )
    from quodeq.analysis.cache.cache_writer import (  # noqa: PLC0415
        CacheWriterSpec,
        build_cache_writer,
    )
    from quodeq.config.paths import default_paths  # noqa: PLC0415
    src_root = Path(server_args.work_dir) if server_args.work_dir else Path.cwd()
    # NOTE: standards_dir must be the standards ROOT (parent of
    # "compiled/"), not server_args.compiled_dir. build_cache_writer /
    # dimension_params_state append "compiled/<dim>.json" themselves;
    # passing compiled_dir here double-appends "compiled" and the
    # params-fingerprint lookup silently misses, keying every entry
    # under the default-thresholds key. --standards-dir is None when
    # not supplied by the caller (back-compat: no params fingerprint).
    standards_dir = Path(server_args.standards_dir) if server_args.standards_dir else None
    spec = CacheWriterSpec(
        cache_root=Path(server_args.cache_root),
        src_root=src_root,
        standards_dir=standards_dir,
        dimension=server_args.dimension,
        model_id=server_args.model_id,
        language=server_args.language or "",
        # This subprocess is its own composition root: no RunConfig
        # crosses the process boundary, so resolve the same default the
        # parent's RunConfig.prompts_dir carries.
        prompts_dir=default_paths().prompts_dir,
    )
    return build_cache_writer(spec)


def _build_router(
    findings_fh, findings_path: Path, ctx: CompiledContext,
    server_args: ServerArgs,
) -> FindingsRouter:
    """Construct a FindingsRouter wired to the event log and (when configured)
    the per-file synchronous cache writer.

    The findings_path is `<run_dir>/evidence/<dim>_evidence.jsonl`, so the run
    directory is its grandparent and the project directory its great-grandparent.
    The event log lives at `<run_dir>/events.jsonl`.
    """
    run_dir = Path(findings_path).parent.parent
    project_dir = run_dir.parent
    # The strict reader raises on a failed open, so the per-run memo skips the
    # run instead of remembering it as having no dismissals.
    ctx.precedent_fingerprints = load_precedent_fingerprints(
        project_dir, read_dismissed=read_dismissed_snippets_strict,
        source_stamp=dismissed_source_stamp,
    )
    # This server is its own process: its env is the run's env.
    ctx.precedent_corpus = load_precedent_corpus(project_dir, run_dir, settings=precedent_settings())
    ctx.on_precedent_match = precedent_match_hook(project_dir)
    from quodeq.data.events.writer import EventLogWriter  # noqa: PLC0415
    event_log = EventLogWriter(run_dir / "events.jsonl")

    cache_writer = _resolve_dimension_cache_writer(server_args)

    return FindingsRouter(
        findings_fh, context=ctx, event_log=event_log,
        on_file_done=cache_writer,
    )


if __name__ == "__main__":
    main()
