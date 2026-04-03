"""Subagent processing path -- runs a dimension via N parallel subagents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from quodeq.analysis._types import RunConfig
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
    _dispatch_verification_pool,
    _load_and_filter_previous,
    _run_verification_pool,
    _run_verification_step,
)


@dataclass
class DimensionCallbacks:
    """Grouped callbacks for single-agent dimension processing fallback."""
    build_prompt: Callable[..., str]
    run_analysis: Callable[..., tuple[Any, Any]]
    parse_evidence: Callable[..., Evidence | None]


def process_consolidated_dimensions(
    config: RunConfig, dimensions: list[str], ctx: Any,
) -> dict[str, Evidence]:
    """Run all dimensions in a single pass -- files read once, not per dimension."""
    from quodeq.analysis.subagents._consolidated import process_consolidated_dimensions as _impl
    return _impl(config, dimensions, ctx)


def process_dimension_with_subagents(
    config: RunConfig, dim_id: str, idx: int, ctx: Any,
    callbacks: DimensionCallbacks,
) -> Evidence | None:
    """Run dimension analysis using N parallel subagents.

    Falls back to single-agent path (via provided callbacks) when no source
    files are detected for the queue.
    """
    evidence_dir = config.work_dir or config.src

    # 1. List source files
    files, extensions = _list_source_files(config, dim_id)
    if not files:
        log_warning(
            f"[{idx}/{ctx.total}] {dim_id} -- no source files for subagent queue"
            f" (src={config.src}, language={config.language}, extensions={extensions})"
        )
        prompt = callbacks.build_prompt(config, dim_id, ctx)
        stream_file, jsonl_file = callbacks.run_analysis(config, dim_id, prompt, idx, ctx)
        return callbacks.parse_evidence(config, dim_id, stream_file, jsonl_file, ctx)

    # 2-3. Load previous findings and run verification
    verify_results = _run_verification_step(config, dim_id, evidence_dir, files)

    # 4. Create queue with per-agent file limit for context rotation
    queue_path = evidence_dir / f"{dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(files))
    FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
    log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued for {config.options.max_subagents} subagents")

    # 5. Build prompt and launch main analysis pool
    prompt = _build_subagent_prompt(config, dim_id, ctx)
    params = LaunchPoolParams(
        evidence_dir=evidence_dir, queue_path=queue_path,
        prompt=prompt, max_files_per_agent=files_per_agent,
    )
    pool, results = _launch_pool(config, dim_id, params)

    # 6. Collect and return evidence (includes both verified + new findings)
    all_results = verify_results + results
    return _collect_evidence(config, dim_id, evidence_dir, _CollectionContext(results=all_results, ctx=ctx, files=files))
