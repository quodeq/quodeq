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
    _dispatch_mini_verify,
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

    # 2. Load previous findings, partition by fingerprint
    from quodeq.analysis.subagents.verify import (
        partition_findings_by_fingerprint, write_carry_forward_findings,
    )
    from quodeq.analysis.subagents._finding_classifier import classify_findings

    prev_findings = _load_and_filter_previous(config, dim_id, evidence_dir)
    carry_forward: list[dict] = []
    needs_verify: list[dict] = []
    if prev_findings:
        from quodeq.analysis.fingerprint import find_previous_fingerprint
        prev_fp, _ = find_previous_fingerprint(evidence_dir, dim_id)
        carry_forward, needs_verify = partition_findings_by_fingerprint(
            prev_findings, prev_fp, config.src,
            standards_dir=config.standards_dir, dimension=dim_id,
        )
    if carry_forward:
        written = write_carry_forward_findings(carry_forward, evidence_dir, dim_id)
        log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {written} findings carried forward")

    # 3. Split needs_verify into inline (in queue) vs mini-verify (not in queue)
    queue_files = set(files)
    inline_findings, mini_verify_findings = classify_findings(needs_verify, queue_files)

    # 4. Create analysis queue
    queue_path = evidence_dir / f"{dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(files))
    FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
    log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued, {len(inline_findings)} inline findings")

    # 5. Build prompt with inline findings and launch analysis pool
    prompt = _build_subagent_prompt(config, dim_id, ctx, inline_findings=inline_findings)
    params = LaunchPoolParams(
        evidence_dir=evidence_dir, queue_path=queue_path,
        prompt=prompt, max_files_per_agent=files_per_agent,
    )
    pool, results = _launch_pool(config, dim_id, params)

    # 6. Save fingerprint eagerly so it survives cancel/timeout
    from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint
    fp = build_fingerprint(config.src, files, dim_id, config.standards_dir)
    save_fingerprint(fp, evidence_dir)

    # 7. Mini-verify for changed files not in analysis queue
    if mini_verify_findings:
        verify_results = _dispatch_mini_verify(config, dim_id, evidence_dir, mini_verify_findings)
        results = results + verify_results

    # 8. Collect evidence (also saves fingerprint, but we saved it eagerly above)
    return _collect_evidence(config, dim_id, evidence_dir, _CollectionContext(results=results, ctx=ctx, files=files))
