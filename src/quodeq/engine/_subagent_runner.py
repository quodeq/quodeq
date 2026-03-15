"""Subagent processing path -- runs a dimension via N parallel subagents.

Extracted from runner.py to keep module size within maintainability limits.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from quodeq.engine.analysis import AnalysisConfig, count_files_from_stream
from quodeq.engine.evidence import Evidence
from quodeq.engine.evidence_parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.engine.file_queue import FileQueue
from quodeq.engine.plugin_detector import list_source_files
from quodeq.engine.plugin_loader import load_plugin
from quodeq.engine.prompt_builder import PromptContext, build_analysis_prompt, load_template
from quodeq.engine.subagent_pool import PoolPaths, SubagentPool
from quodeq.shared.logging import log_info, log_warning

if TYPE_CHECKING:
    from quodeq.engine.runner import RunConfig


@dataclass
class DimensionCallbacks:
    """Grouped callbacks for single-agent dimension processing fallback."""
    build_prompt: Callable[..., str]
    run_analysis: Callable[..., tuple[Path, Path]]
    parse_evidence: Callable[..., Evidence | None]


def _default_subagent_model() -> str:
    """Return the subagent model, reading from env at call time (not import time)."""
    return os.environ.get("QUODEQ_SUBAGENT_MODEL", "claude-haiku-4-5")


def _list_plugin_files(config: RunConfig, ctx_total: int, dim_id: str, idx: int) -> tuple[list[str], set[str]]:
    """List source files for the subagent queue.

    Returns (files, extensions) or ([], extensions) if none found.
    """
    plugin_dir = config.evaluators_dir / config.plugin_id
    plugin_data = load_plugin(plugin_dir)
    extensions = set(plugin_data.get("detects", {}).get("extensions", []))
    files = list_source_files(config.src, extensions) if extensions else []
    return files, extensions


def _build_subagent_prompt(config: RunConfig, dim_id: str, ctx: Any) -> str:
    """Build the prompt for subagent analysis using the subagent.md template."""
    subagent_template = load_template(template_name="subagent.md")
    return build_analysis_prompt(
        subagent_template,
        PromptContext(
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            analysis_md=ctx.analysis_md,
            standards_dir=config.standards_dir,
        ),
    )


def _launch_pool(config: RunConfig, dim_id: str, evidence_dir: Path, queue_path: Path, prompt: str) -> tuple[Any, list[Any]]:
    """Create and run a SubagentPool, returning its results."""
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    subagent_model = config.options.subagent_model or _default_subagent_model()
    base_ac = AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
    )
    pool = SubagentPool(
        n_agents=config.options.n_subagents,
        paths=PoolPaths(work_dir=config.src, evidence_dir=evidence_dir, queue_path=queue_path),
        prompt=prompt,
        dimension=dim_id,
        config=base_ac,
    )
    return pool, pool.run()


def _collect_evidence(config: RunConfig, dim_id: str, evidence_dir: Path, results: list[Any], ctx: Any) -> Evidence:
    """Deduplicate JSONL, count files read, and parse into Evidence."""
    # Imported here to avoid circular import: runner -> _subagent_runner -> runner
    from quodeq.engine.runner import cleanup_stream

    merged_jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
    SubagentPool.deduplicate_jsonl(merged_jsonl)

    total_files_read = 0
    for r in results:
        if r.stream_file.exists():
            total_files_read += count_files_from_stream(r.stream_file)
            cleanup_stream(r.stream_file)

    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    ev = parse_jsonl_to_evidence(
        merged_jsonl,
        EvidenceContext(
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=total_files_read,
        ),
        compiled_dir=compiled_dir,
    )
    ev.plugin_name = ctx.plugin_name
    return ev


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
    files, extensions = _list_plugin_files(config, ctx.total, dim_id, idx)
    if not files:
        log_warning(
            f"[{idx}/{ctx.total}] {dim_id} -- no source files for subagent queue"
            f" (src={config.src}, plugin={config.plugin_id}, extensions={extensions})"
        )
        prompt = callbacks.build_prompt(config, dim_id, ctx)
        stream_file, jsonl_file = callbacks.run_analysis(config, dim_id, prompt, idx, ctx)
        return callbacks.parse_evidence(config, dim_id, stream_file, jsonl_file, ctx)

    # 2. Create queue
    queue_path = evidence_dir / f"{dim_id}_queue.json"
    FileQueue(queue_path, files)
    log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued for {config.options.n_subagents} subagents")

    # 3. Build prompt and launch pool
    prompt = _build_subagent_prompt(config, dim_id, ctx)
    pool, results = _launch_pool(config, dim_id, evidence_dir, queue_path, prompt)

    # 4. Collect and return evidence
    return _collect_evidence(config, dim_id, evidence_dir, results, ctx)
