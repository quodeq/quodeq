"""Subagent processing path -- runs a dimension via N parallel subagents."""
from __future__ import annotations

from dataclasses import dataclass
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


def process_consolidated_dimensions(
    config: RunConfig, dimensions: list[str], ctx: Any,
) -> dict[str, Evidence]:
    """Run all dimensions in a single pass -- files read once, not per dimension."""
    return _process_consolidated_impl(config, dimensions, ctx)


def _prepare_findings_and_queue(
    config: RunConfig, dim_id: str, idx: int, ctx: Any,
    files: list[str], evidence_dir: Path,
) -> tuple[list[dict], list[dict], Path, int]:
    """Load previous findings, partition by fingerprint, and create the file queue.

    Returns (inline_findings, mini_verify_findings, queue_path, files_per_agent).
    """
    prev_findings = _load_and_filter_previous(config, dim_id, evidence_dir)
    carry_forward: list[dict] = []
    needs_verify: list[dict] = []
    if prev_findings:
        prev_fp, _ = find_previous_fingerprint(evidence_dir, dim_id)
        carry_forward, needs_verify = partition_findings_by_fingerprint(
            prev_findings, prev_fp, config.src,
            standards_dir=config.standards_dir, dimension=dim_id,
        )
    if carry_forward:
        written = write_carry_forward_findings(carry_forward, evidence_dir, dim_id)
        log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {written} findings carried forward")

    queue_files = set(files)
    inline_findings, mini_verify_findings = classify_findings(needs_verify, queue_files)

    queue_path = evidence_dir / f"{dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(files))
    FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
    log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued, {len(inline_findings)} inline findings")

    return inline_findings, mini_verify_findings, queue_path, files_per_agent


def _execute_pool_and_collect(
    config: RunConfig, dim_id: str, ctx: Any,
    files: list[str], evidence_dir: Path,
    inline_findings: list[dict], mini_verify_findings: list[dict],
    queue_path: Path, files_per_agent: int,
) -> Evidence | None:
    """Build prompt, launch pool, save fingerprint, and collect evidence."""
    prompt = _build_subagent_prompt(config, dim_id, ctx, inline_findings=inline_findings)
    params = LaunchPoolParams(
        evidence_dir=evidence_dir, queue_path=queue_path,
        prompt=prompt, max_files_per_agent=files_per_agent,
        all_files=files,
    )
    pool, results = _launch_pool(config, dim_id, params)

    fp = build_fingerprint(config.src, files, dim_id, config.standards_dir)
    save_fingerprint(fp, evidence_dir)

    if mini_verify_findings:
        verify_results = _dispatch_mini_verify(config, dim_id, evidence_dir, mini_verify_findings)
        results = results + verify_results

    return _collect_evidence(config, dim_id, evidence_dir, _CollectionContext(results=results, ctx=ctx, files=files))


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

    inline_findings, mini_verify_findings, queue_path, files_per_agent = \
        _prepare_findings_and_queue(config, dim_id, idx, ctx, files, evidence_dir)

    return _execute_pool_and_collect(
        config, dim_id, ctx, files, evidence_dir,
        inline_findings, mini_verify_findings, queue_path, files_per_agent,
    )
