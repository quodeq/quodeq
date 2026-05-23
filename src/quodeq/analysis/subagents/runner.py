"""Subagent processing path -- runs a dimension via N parallel subagents.

Post-V2 (B6.2b): the verify-pool is gone. V2's content-addressed cache
already invalidates on file/standards/prompts changes, triggering a
full fresh dispatch. The V1 "carry-forward + verify-when-rules-change"
optimization no longer earns its complexity.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quodeq.analysis._types import RunConfig
from quodeq.core.evidence.model import Evidence
from quodeq.shared.logging import log_info, log_warning

# Re-exports from split modules -- keep the public API stable
from quodeq.analysis.subagents._source_files import _list_source_files  # noqa: F401
from quodeq.analysis.subagents._prompts import _build_subagent_prompt  # noqa: F401
from quodeq.analysis.subagents._pool_launcher import (  # noqa: F401
    LaunchPoolParams,
    _compute_files_per_agent,
    _default_subagent_model,
    _launch_pool,
    _collect_all_evidence,
)
from quodeq.analysis.subagents._evidence_collector import (  # noqa: F401
    _CollectionContext,
    _collect_evidence,
)
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents._consolidated import (
    process_consolidated_dimensions as _process_consolidated_impl,
)


@dataclass
class DimensionCallbacks:
    """Grouped callbacks for single-agent dimension processing fallback."""
    build_prompt: Callable[..., str]
    run_analysis: Callable[..., tuple[Any, Any]]
    parse_evidence: Callable[..., Evidence | None]


@dataclass
class _DimensionContext:
    """Grouped parameters for dimension processing."""
    dim_id: str
    idx: int
    ctx: Any
    files: list[str]
    evidence_dir: Path


@dataclass
class _PoolExecutionParams:
    """Grouped parameters for pool execution and evidence collection."""
    queue_path: Path
    files_per_agent: int


def process_consolidated_dimensions(
    config: RunConfig, dimensions: list[str], ctx: Any,
) -> dict[str, Evidence]:
    """Run all dimensions in a single pass -- files read once, not per dimension."""
    return _process_consolidated_impl(config, dimensions, ctx)


def _prepare_findings_and_queue(
    config: RunConfig, dc: _DimensionContext,
) -> _PoolExecutionParams:
    """Build the file queue for the pool. No prior-findings logic — V2's
    cache hit/miss already determined which files need dispatch."""
    queue_path = dc.evidence_dir / f"{dc.dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(dc.files))
    FileQueue(queue_path, dc.files, max_files_per_agent=files_per_agent)
    log_info(
        f"  [{dc.idx}/{dc.ctx.total}] {dc.dim_id} -- {len(dc.files)} files queued",
    )
    return _PoolExecutionParams(
        queue_path=queue_path, files_per_agent=files_per_agent,
    )


def _execute_pool_and_collect(
    config: RunConfig, dc: _DimensionContext, pool_params: _PoolExecutionParams,
) -> Evidence | None:
    """Build prompt, launch pool, collect evidence."""
    prompt = _build_subagent_prompt(config, dc.dim_id, dc.ctx)
    params = LaunchPoolParams(
        evidence_dir=dc.evidence_dir, queue_path=pool_params.queue_path,
        prompt=prompt, max_files_per_agent=pool_params.files_per_agent,
        all_files=dc.files,
    )
    pool, results = _launch_pool(config, dc.dim_id, params)
    return _collect_evidence(
        config, dc.dim_id, dc.evidence_dir,
        _CollectionContext(
            results=results, ctx=dc.ctx, files=dc.files,
            exit_reason=pool.exit_reason,
        ),
    )


def process_dimension_with_subagents(
    config: RunConfig, dim_id: str, idx: int, ctx: Any,
    callbacks: DimensionCallbacks,
) -> Evidence | None:
    """Run dimension analysis using N parallel subagents.

    Falls back to single-agent path (via provided callbacks) when no source
    files are detected for the queue.
    """
    evidence_dir = config.work_dir or config.src

    files, extensions = _list_source_files(config, dim_id)
    if not files:
        log_warning(
            f"[{idx}/{ctx.total}] {dim_id} -- no source files for subagent queue"
            f" (src={config.src}, language={config.language}, extensions={extensions})"
        )
        prompt = callbacks.build_prompt(config, dim_id, ctx)
        stream_file, jsonl_file = callbacks.run_analysis(config, dim_id, prompt, idx, ctx)
        return callbacks.parse_evidence(config, dim_id, stream_file, jsonl_file, ctx)

    dc = _DimensionContext(dim_id=dim_id, idx=idx, ctx=ctx, files=files, evidence_dir=evidence_dir)
    pool_params = _prepare_findings_and_queue(config, dc)

    return _execute_pool_and_collect(config, dc, pool_params)
