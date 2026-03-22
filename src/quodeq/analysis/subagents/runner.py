"""Subagent processing path -- runs a dimension via N parallel subagents.

Extracted from runner.py to keep module size within maintainability limits.
"""
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
from quodeq.analysis.subagents.pool import PoolPaths, SubagentPool
from quodeq.shared.logging import log_info, log_success, log_warning

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig

_MAX_FILES_PER_AGENT = 30
_VERIFY_MAX_FILES_PER_AGENT = 40  # verification is lighter, can handle more files
_VERIFY_MAX_TURNS = 100           # verification tasks are quick but need enough turns
_VERIFY_MAX_DURATION = 600        # 10 minutes max for verification pool
_VERIFY_N_AGENTS = 5              # match main pool agent count for faster verification


def _compute_files_per_agent(total_files: int) -> int:
    """Compute adaptive max files per agent based on project size.

    Larger projects get higher limits to reduce context rotation overhead
    (each rotation spawns a new CLI session with ~8K tokens of fixed cost).
    """
    if total_files <= 0:
        return 0
    if total_files <= 50:
        return total_files
    if total_files <= 200:
        return 50
    if total_files <= 1000:
        return 75
    return 100


@dataclass
class DimensionCallbacks:
    """Grouped callbacks for single-agent dimension processing fallback."""
    build_prompt: Callable[..., str]
    run_analysis: Callable[..., tuple[Path, Path]]
    parse_evidence: Callable[..., Evidence | None]


def _default_subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override, or None to use the client's default."""
    return (env or os.environ).get("QUODEQ_SUBAGENT_MODEL") or None


def _list_source_files(config: RunConfig, dim_id: str) -> tuple[list[str], set[str]]:
    """List source files for the subagent queue from the target or manifest.

    Returns (files, extensions) or ([], set()) if none found.
    """
    # Prefer target-scoped files when available
    if config.target is not None and config.target.source_files:
        extensions = set(config.target.language_stats.keys()) if config.target.language_stats else set()
        return config.target.source_files, extensions

    if config.manifest is not None and config.manifest.source_files:
        extensions = set(config.manifest.language_stats.keys()) if config.manifest.language_stats else set()
        return config.manifest.source_files, extensions

    return [], set()


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


def _launch_pool(config: RunConfig, dim_id: str, evidence_dir: Path, queue_path: Path, prompt: str, max_files_per_agent: int = 30) -> tuple[Any, list[Any]]:
    """Create and run a SubagentPool, returning its results."""
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    subagent_model = config.options.subagent_model or _default_subagent_model()
    base_ac = AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
        max_files_per_agent=max_files_per_agent,
    )
    pool = SubagentPool(
        n_agents=config.options.max_subagents,
        paths=PoolPaths(work_dir=config.src, evidence_dir=evidence_dir, queue_path=queue_path),
        prompt=prompt,
        dimension=dim_id,
        config=base_ac,
    )
    return pool, pool.run()


def _fast_model(env: dict[str, str] | None = None) -> str:
    """Return the fast/verification model. Defaults to 'haiku'."""
    return (env or os.environ).get("QUODEQ_FAST_MODEL", "haiku")


def _run_verification_pool(
    config: RunConfig, dim_id: str, evidence_dir: Path,
    files_to_verify: list[str], manifest_path: Path,
) -> list[Any]:
    """Launch a fast verification pool to re-check previous findings.

    Uses the fast model (haiku by default) with a smaller pool.
    Confirmed findings are written to JSONL via MCP → appear on dashboard.
    """
    from quodeq.analysis.subagents.verify import build_verify_prompt

    queue_path = evidence_dir / f"{dim_id}_verify_queue.json"
    FileQueue(queue_path, files_to_verify, max_files_per_agent=_VERIFY_MAX_FILES_PER_AGENT)

    prompt = build_verify_prompt(manifest_path, dim_id)
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    fast = _fast_model()

    ac = AnalysisConfig(
        compiled_dir=compiled_dir,
        max_turns=_VERIFY_MAX_TURNS,
        max_duration=_VERIFY_MAX_DURATION,
        ai_model=fast,
        dimension=dim_id,
    )

    n_agents = min(_VERIFY_N_AGENTS, len(files_to_verify))
    pool = SubagentPool(
        n_agents=n_agents,
        paths=PoolPaths(work_dir=config.src, evidence_dir=evidence_dir, queue_path=queue_path),
        prompt=prompt,
        dimension=dim_id,
        config=ac,
    )
    return pool.run()


def _collect_evidence(config: RunConfig, dim_id: str, evidence_dir: Path, results: list[Any], ctx: Any) -> Evidence:
    """Deduplicate JSONL, count files read, and parse into Evidence."""
    from quodeq.engine._runner_markers import cleanup_stream

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
            language=config.language,
            repository=str(config.src),
            date_str=ctx.date_str,
            source_file_count=config.source_file_count,
            files_read=total_files_read,
            module=config.target.name if config.target else "",
        ),
        compiled_dir=compiled_dir,
    )
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
    files, extensions = _list_source_files(config, dim_id)
    if not files:
        log_warning(
            f"[{idx}/{ctx.total}] {dim_id} -- no source files for subagent queue"
            f" (src={config.src}, language={config.language}, extensions={extensions})"
        )
        prompt = callbacks.build_prompt(config, dim_id, ctx)
        stream_file, jsonl_file = callbacks.run_analysis(config, dim_id, prompt, idx, ctx)
        return callbacks.parse_evidence(config, dim_id, stream_file, jsonl_file, ctx)

    # 2. Load and pre-filter previous findings for AI verification
    from quodeq.analysis.subagents.verify import (
        load_previous_findings_for_dimension, _group_by_file, _write_verify_manifest,
    )
    prev_findings = load_previous_findings_for_dimension(config, dim_id, evidence_dir)

    # 3. Run AI verification pool (fast model) if there are findings to verify
    verify_results: list = []
    if prev_findings:
        grouped = _group_by_file(prev_findings)
        manifest_path = evidence_dir / f"{dim_id}_verify_manifest.json"
        _write_verify_manifest(grouped, manifest_path)
        files_to_verify = list(grouped.keys())
        log_info(f"  [{dim_id}] Launching fast verification pool for {len(prev_findings)} findings across {len(files_to_verify)} files")
        verify_results = _run_verification_pool(config, dim_id, evidence_dir, files_to_verify, manifest_path)
        log_success(f"  [{dim_id}] Verification pool complete")

    # 4. Create queue with per-agent file limit for context rotation
    queue_path = evidence_dir / f"{dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(files))
    FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
    log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued for {config.options.max_subagents} subagents")

    # 5. Build prompt and launch main analysis pool
    prompt = _build_subagent_prompt(config, dim_id, ctx)
    pool, results = _launch_pool(config, dim_id, evidence_dir, queue_path, prompt, max_files_per_agent=files_per_agent)

    # 6. Collect and return evidence (includes both verified + new findings)
    all_results = verify_results + results
    return _collect_evidence(config, dim_id, evidence_dir, all_results, ctx)
