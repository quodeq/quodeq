"""Subagent processing path -- runs a dimension via N parallel subagents."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from quodeq.analysis._types import RunConfig
from quodeq.analysis.fingerprint import build_fingerprint, find_previous_fingerprint, save_fingerprint
from quodeq.analysis.subagents._finding_classifier import classify_findings
from quodeq.analysis.subagents.verify import (
    partition_findings_by_fingerprint, write_carry_forward_findings,
)
from quodeq.core.evidence.model import Evidence
from quodeq.analysis.subagents.file_queue import FileQueue
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
from quodeq.analysis.subagents._verification import (  # noqa: F401
    _dispatch_mini_verify,
    _dispatch_verification_pool,
    _load_and_filter_previous,
    _run_verification_pool,
    _run_verification_step,
)
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
    inline_findings: list[dict]
    mini_verify_findings: list[dict]
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
    """Load previous findings, partition by fingerprint, and create the file queue."""
    # Clean scan (incremental=False) means "ignore everything from before",
    # not "re-verify everything from before". Skip the loader so prior
    # findings don't get inlined into prompts as needs_verify entries.
    if config.options.incremental:
        prev_findings = _load_and_filter_previous(config, dc.dim_id, dc.evidence_dir)
    else:
        prev_findings = []
    carry_forward: list[dict] = []
    needs_verify: list[dict] = []
    if prev_findings:
        prev_fp, _ = find_previous_fingerprint(dc.evidence_dir, dc.dim_id)
        carry_forward, needs_verify = partition_findings_by_fingerprint(
            prev_findings, prev_fp, config.src,
            standards_dir=config.standards_dir, dimension=dc.dim_id,
        )
    if carry_forward:
        written = write_carry_forward_findings(carry_forward, dc.evidence_dir, dc.dim_id)
        log_info(f"  [{dc.idx}/{dc.ctx.total}] {dc.dim_id} -- {written} findings carried forward")

    queue_files = set(dc.files)
    inline_findings, mini_verify_findings = classify_findings(needs_verify, queue_files)

    queue_path = dc.evidence_dir / f"{dc.dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(dc.files))
    FileQueue(queue_path, dc.files, max_files_per_agent=files_per_agent)
    log_info(f"  [{dc.idx}/{dc.ctx.total}] {dc.dim_id} -- {len(dc.files)} files queued, {len(inline_findings)} inline findings")

    return _PoolExecutionParams(
        inline_findings=inline_findings, mini_verify_findings=mini_verify_findings,
        queue_path=queue_path, files_per_agent=files_per_agent,
    )


def _execute_pool_and_collect(
    config: RunConfig, dc: _DimensionContext, pool_params: _PoolExecutionParams,
) -> Evidence | None:
    """Build prompt, launch pool, save fingerprint, and collect evidence."""
    prompt = _build_subagent_prompt(config, dc.dim_id, dc.ctx, inline_findings=pool_params.inline_findings)
    params = LaunchPoolParams(
        evidence_dir=dc.evidence_dir, queue_path=pool_params.queue_path,
        prompt=prompt, max_files_per_agent=pool_params.files_per_agent,
        all_files=dc.files,
    )
    pool, results = _launch_pool(config, dc.dim_id, params)

    fp = build_fingerprint(config.src, dc.files, dc.dim_id, config.standards_dir)
    save_fingerprint(fp, dc.evidence_dir)

    if pool_params.mini_verify_findings:
        verify_results = _dispatch_mini_verify(config, dc.dim_id, dc.evidence_dir, pool_params.mini_verify_findings)
        results = results + verify_results

    return _collect_evidence(config, dc.dim_id, dc.evidence_dir, _CollectionContext(results=results, ctx=dc.ctx, files=dc.files))


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
