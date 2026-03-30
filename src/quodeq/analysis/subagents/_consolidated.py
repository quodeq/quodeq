"""Consolidated multi-dimension analysis — extracted from subagents/runner.py."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET
from quodeq.core.evidence.model import Evidence
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence_by_dimension
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.prompts.builder import PromptContext, build_consolidated_prompt
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.shared.logging import log_info, log_warning

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig


def _build_consolidated_config(
    config: "RunConfig", dimensions: list[str], files_per_agent: int,
) -> AnalysisConfig:
    """Build AnalysisConfig for consolidated mode."""
    from quodeq.analysis.subagents.runner import _default_subagent_model

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    subagent_model = config.options.subagent_model or _default_subagent_model()
    pool_budget_val = config.options.pool_budget
    return AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
        dimension=",".join(dimensions),
        max_files_per_agent=files_per_agent,
        pool_budget=pool_budget_val if pool_budget_val is not None else _DEFAULT_POOL_BUDGET,
    )


def _collect_consolidated_results(
    config: "RunConfig", dimensions: list[str], ctx: Any,
    results: list[Any], evidence_dir: Path,
) -> dict[str, Evidence]:
    """Deduplicate and parse consolidated results into per-dimension Evidence."""
    from quodeq.analysis.stream.counters import count_files_in_stream
    from quodeq.engine._runner_markers import cleanup_stream

    merged_jsonl = evidence_dir / "consolidated_evidence.jsonl"
    SubagentPool.deduplicate_jsonl(merged_jsonl)

    total_files_read = 0
    for r in results:
        if r.stream_file.exists():
            total_files_read += len(count_files_in_stream(r.stream_file))
            cleanup_stream(r.stream_file)

    ev_ctx = EvidenceContext(
        language=config.language,
        repository=str(config.src),
        date_str=ctx.date_str,
        source_file_count=config.source_file_count,
        files_read=total_files_read,
        module=config.target.name if config.target else "",
    )

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    return parse_jsonl_to_evidence_by_dimension(
        merged_jsonl, ev_ctx, compiled_dir=compiled_dir,
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
    from quodeq.analysis.subagents.runner import _list_source_files, _compute_files_per_agent

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
    base_ac = _build_consolidated_config(config, dimensions, files_per_agent)
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
    return _collect_consolidated_results(config, dimensions, ctx, results, evidence_dir)
