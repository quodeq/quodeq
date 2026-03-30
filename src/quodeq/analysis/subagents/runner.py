"""Subagent processing path -- runs a dimension via N parallel subagents."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from quodeq.analysis.subprocess import AnalysisConfig, count_files_from_stream
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.analysis.subagents.priority import PriorityContext, prioritize_files
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET
from quodeq.shared.logging import log_info, log_success, log_warning

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig

_MAX_FILES_PER_AGENT = 30
_MAX_FILES_PER_AGENT_CAP = 50


def _compute_files_per_agent(total_files: int) -> int:
    """Compute adaptive max files per agent. Capped to avoid turn limits."""
    return min(total_files, _MAX_FILES_PER_AGENT_CAP) if total_files > 0 else 0


# Re-export verification helpers (extracted to _verification.py for file-length limits)
from quodeq.analysis.subagents._verification import (  # noqa: E402,F401
    _dispatch_verification_pool,
    _load_and_filter_previous,
    _run_verification_pool,
    _run_verification_step,
)


@dataclass
class DimensionCallbacks:
    """Grouped callbacks for single-agent dimension processing fallback."""
    build_prompt: Callable[..., str]
    run_analysis: Callable[..., tuple[Path, Path]]
    parse_evidence: Callable[..., Evidence | None]


def _default_subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override, or None to use the client's default."""
    return (env or os.environ).get("QUODEQ_SUBAGENT_MODEL") or None


def _list_source_files(config: RunConfig, dim_id: str, *, ignore_file_filter: bool = False) -> tuple[list[str], set[str]]:
    """List source files for the subagent queue from the target or manifest.

    Returns (files, extensions) or ([], set()) if none found.
    Files are returned in priority order (most important first).
    """
    # Prefer target-scoped files when available
    if config.target is not None and config.target.source_files:
        files = config.target.source_files
        extensions = set(config.target.language_stats.keys()) if config.target.language_stats else set()
    elif config.manifest is not None and config.manifest.source_files:
        files = config.manifest.source_files
        extensions = set(config.manifest.language_stats.keys()) if config.manifest.language_stats else set()
    else:
        return [], set()

    # Prioritize files: most important first
    category = None
    if config.target and config.target.category:
        category = config.target.category
    elif config.manifest:
        category = config.manifest.category

    evidence_dir = config.work_dir or config.src
    files = prioritize_files(
        files, config.src, dim_id,
        context=PriorityContext(
            category=category,
            language=config.language,
            evidence_dir=evidence_dir,
            config=config,
        ),
    )

    # Incremental mode: filter to only changed + dependent files
    if not ignore_file_filter and config.options.incremental_file_filter is not None:
        filter_set = config.options.incremental_file_filter
        files = [f for f in files if f in filter_set]

    return files, extensions


def _build_subagent_prompt(config: RunConfig, dim_id: str, ctx: Any) -> str:
    """Build the prompt for subagent analysis using the cached subagent.md template."""
    return build_analysis_prompt(
        ctx.subagent_template,
        PromptContext(
            language=config.language,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            standards_dir=config.standards_dir,
            manifest=config.manifest,
            target=config.target,
            work_dir=config.work_dir or config.src,
        ),
    )


@dataclass
class LaunchPoolParams:
    """Grouped parameters for launching a subagent pool."""
    evidence_dir: Path
    queue_path: Path
    prompt: str
    max_files_per_agent: int = 30


def _launch_pool(config: RunConfig, dim_id: str, params: LaunchPoolParams) -> tuple[Any, list[Any]]:
    """Create and run a SubagentPool, returning its results."""
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    subagent_model = config.options.subagent_model or _default_subagent_model()
    base_ac = AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
        max_files_per_agent=params.max_files_per_agent,
        pool_budget=config.options.pool_budget if config.options.pool_budget is not None else _DEFAULT_POOL_BUDGET,
    )
    pool = SubagentPool(
        paths=PoolPaths(work_dir=config.src, evidence_dir=params.evidence_dir, queue_path=params.queue_path),
        options=PoolOptions(
            n_agents=config.options.max_subagents,
            prompt=params.prompt,
            dimension=dim_id,
        ),
        config=base_ac,
    )
    return pool, pool.run()


def _collect_evidence(
    config: RunConfig, dim_id: str, evidence_dir: Path,
    results: list[Any], ctx: Any, files: list[str] | None = None,
) -> Evidence:
    """Deduplicate JSONL, count files read, save fingerprint, and parse into Evidence."""
    from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint
    from quodeq.engine._runner_markers import cleanup_stream

    merged_jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
    SubagentPool.deduplicate_jsonl(merged_jsonl)

    total_files_read = 0
    for r in results:
        if r.stream_file.exists():
            total_files_read += count_files_from_stream(r.stream_file)
            cleanup_stream(r.stream_file)

    # Save fingerprint so next run can carry forward unchanged-file findings
    if files:
        fp = build_fingerprint(config.src, files, dim_id, config.standards_dir)
        save_fingerprint(fp, evidence_dir)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    ev = parse_jsonl_to_evidence(
        merged_jsonl,
        EvidenceContext(
            language=config.language,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=total_files_read,
            module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )
    return ev


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
    return _collect_evidence(config, dim_id, evidence_dir, all_results, ctx, files=files)
