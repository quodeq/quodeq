"""Consolidated multi-dimension analysis — extracted from subagents/runner.py."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.shared.constants import _DEFAULT_TIME_LIMIT
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence_by_dimension
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.prompts.builder import PromptContext, build_consolidated_prompt
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.analysis.subagents._pool_launcher import _default_subagent_model, _compute_files_per_agent
from quodeq.analysis.subagents._source_files import _list_source_files
from quodeq.engine._runner_markers import cleanup_stream
from quodeq.shared.logging import log_info, log_warning


@dataclass(frozen=True)
class _ConsolidatedPaths:
    """Paths for consolidated evidence collection."""
    evidence_dir: Path
    compiled_dir: "Path | None" = None


@dataclass(frozen=True)
class _ConsolidatedRunContext:
    """Grouped context for consolidated result collection."""
    dimensions: list[str]
    ctx: Any
    results: list[Any]
    files: list[str]
    exit_reason: str | None = None


def _build_consolidated_config(
    config: "RunConfig", dimensions: list[str], files_per_agent: int,
    compiled_dir: "Path | None" = None,
) -> AnalysisConfig:
    """Build AnalysisConfig for consolidated mode."""
    subagent_model = config.options.subagent_model or _default_subagent_model() or config.options.ai_model
    time_limit_val = config.options.time_limit
    return AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
        dimension=",".join(dimensions),
        max_files_per_agent=files_per_agent,
        time_limit=time_limit_val if time_limit_val is not None else _DEFAULT_TIME_LIMIT,
        deadline_at=config.options.deadline_at,
    )


def _collect_consolidated_results(
    config: "RunConfig", run_ctx: _ConsolidatedRunContext, paths: _ConsolidatedPaths,
) -> dict[str, Evidence]:
    """Deduplicate and parse consolidated results into per-dimension Evidence."""
    merged_jsonl = paths.evidence_dir / "consolidated_evidence.jsonl"
    SubagentPool.deduplicate_jsonl(merged_jsonl)

    total_files_read = 0
    for r in run_ctx.results:
        if r.stream_file.exists():
            total_files_read += len(count_files_in_stream(r.stream_file))
            cleanup_stream(r.stream_file)

    # Determine which files were actually analyzed (from queue + evidence)
    analyzed: set[str] = set()
    queue_path = paths.evidence_dir / "consolidated_queue.json"
    if queue_path.exists():
        try:
            analyzed |= set(FileQueue(queue_path).all_taken_files())
        except (OSError, ValueError, KeyError):
            pass

    # V2 cache owns incremental state via per-file entries written
    # during dispatch; the V1 per-dimension fingerprint write is no
    # longer needed (B6.2).

    ev_ctx = EvidenceContext(
        language=config.language,
        repository=str(config.src),
        date_str=run_ctx.ctx.date_str,
        source_file_count=config.source_file_count,
        files_read=total_files_read,
        module=config.target.name if config.target else "",
        exit_reason=run_ctx.exit_reason,
    )

    return parse_jsonl_to_evidence_by_dimension(
        merged_jsonl, ev_ctx, compiled_dir=paths.compiled_dir,
        evaluators_dir=config.evaluators_dir,
    )


def _build_prompt(config: "RunConfig", dimensions: list[str], ctx: Any) -> str:
    """Build the consolidated prompt for multi-dimension analysis."""
    return build_consolidated_prompt(
        dimensions=dimensions,
        context=PromptContext(
            language=config.language,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension="consolidated",
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            standards_dir=config.standards_dir,
            evaluators_dir=config.evaluators_dir,
            manifest=config.manifest,
            target=config.target,
            work_dir=config.work_dir or config.src,
        ),
    )


def process_consolidated_dimensions(
    config: "RunConfig", dimensions: list[str], ctx: Any,
) -> dict[str, Evidence]:
    """Run all dimensions in a single pass -- files read once, not per dimension."""
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    evidence_dir = config.work_dir or config.src

    # 1. List source files
    files, extensions = _list_source_files(config, dimensions[0])
    if not files:
        log_warning("No source files for consolidated analysis")
        return {}

    # 2. Build consolidated prompt and create file queue
    prompt = _build_prompt(config, dimensions, ctx)
    files_per_agent = _compute_files_per_agent(len(files))
    queue_path = evidence_dir / "consolidated_queue.json"
    FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
    log_info(f"Consolidated analysis: {len(files)} files, {len(dimensions)} dimensions, max {config.options.max_subagents} agents")

    # 3. Build config and launch pool
    base_ac = _build_consolidated_config(config, dimensions, files_per_agent, compiled_dir=compiled_dir)
    pool = SubagentPool(
        paths=PoolPaths(work_dir=config.src, evidence_dir=evidence_dir, queue_path=queue_path),
        options=PoolOptions(
            n_agents=config.options.max_subagents,
            prompt=prompt,
            dimension=dimensions,
        ),
        config=base_ac,
    )
    results = pool.run()

    # 4. Collect and return per-dimension evidence
    run_context = _ConsolidatedRunContext(
        dimensions=dimensions, ctx=ctx, results=results, files=files,
        exit_reason=pool.exit_reason,
    )
    return _collect_consolidated_results(config, run_context, _ConsolidatedPaths(evidence_dir=evidence_dir, compiled_dir=compiled_dir))
