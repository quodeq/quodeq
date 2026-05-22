"""Pool creation, launching, and stream-level evidence collection."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.subprocess import AnalysisConfig, count_files_from_stream
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.shared.constants import _DEFAULT_TIME_LIMIT
from quodeq.shared.logging import log_info
from quodeq.shared.utils import get_ai_cmd

_MAX_FILES_PER_AGENT = 30
_MAX_FILES_PER_AGENT_CAP = 50
_NON_SCOUT_PROVIDERS = tuple(os.environ.get("QUODEQ_NON_SCOUT_PROVIDERS", "codex,gemini").split(","))

# Auto-scale the time limit so large queues don't get killed mid-run.
# A fixed 600s cap chokes any dim with a queue larger than ~80 files
# (observed throughput ≈ 7-12 s/file with 8 agents); the surviving
# pending files keep haunting the next run via the not_analyzed sweep
# and the dim never converges. The user's explicit time_limit is a
# FLOOR — we only ever extend it upward, never shrink it.
_SECONDS_PER_FILE_AUTOSCALE = 12
# Hard upper bound so a runaway queue can't lock up the run for days.
_MAX_AUTO_POOL_BUDGET = 7200  # 2 hours
# time_limit = 0 means "unlimited"; respect that and never scale it.
_UNLIMITED_BUDGET = 0


def _resolve_time_limit(user_budget: int | None, queue_size: int) -> int:
    """Compute the effective time limit for a queue of *queue_size* files.

    The user's `time_limit` (or `_DEFAULT_TIME_LIMIT` if unset) is treated
    as a floor. For large queues we extend it to give each file a fair
    slice of wallclock time, capped at `_MAX_AUTO_POOL_BUDGET`. A user-set
    limit of 0 means "unlimited" and is preserved verbatim.
    """
    base = user_budget if user_budget is not None else _DEFAULT_TIME_LIMIT
    if base == _UNLIMITED_BUDGET:
        return _UNLIMITED_BUDGET
    if queue_size <= 0:
        return base
    needed = queue_size * _SECONDS_PER_FILE_AUTOSCALE
    return min(_MAX_AUTO_POOL_BUDGET, max(base, needed))


def _compute_files_per_agent(total_files: int) -> int:
    """Compute adaptive max files per agent. Capped to avoid turn limits."""
    return min(total_files, _MAX_FILES_PER_AGENT_CAP) if total_files > 0 else 0


def _default_subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override, or None to use the client's default.

    Checks SUBAGENT_MODEL first (set by dashboard/service layer),
    then QUODEQ_SUBAGENT_MODEL (direct env var override).
    """
    _env = env or os.environ
    return _env.get("SUBAGENT_MODEL") or _env.get("QUODEQ_SUBAGENT_MODEL") or None


@dataclass
class LaunchPoolParams:
    """Grouped parameters for launching a subagent pool."""
    evidence_dir: Path
    queue_path: Path
    prompt: str
    max_files_per_agent: int = _MAX_FILES_PER_AGENT
    all_files: list[str] | None = None


def _launch_pool(
    config: RunConfig, dim_id: str, params: LaunchPoolParams,
) -> tuple[Any, list[Any]]:
    """Create and run a SubagentPool, returning its results."""
    compiled_dir = (config.standards_dir / "compiled") if config.standards_dir else None
    subagent_model = config.options.subagent_model or _default_subagent_model() or config.options.ai_model
    queue_size = len(params.all_files) if params.all_files is not None else 0
    time_limit = _resolve_time_limit(config.options.time_limit, queue_size)
    base_user_budget = config.options.time_limit if config.options.time_limit is not None else _DEFAULT_TIME_LIMIT
    if time_limit != base_user_budget and time_limit != _UNLIMITED_BUDGET:
        log_info(
            f"  [{dim_id}] Time limit auto-scaled: {base_user_budget}s → {time_limit}s"
            f" for {queue_size} files"
        )
    base_ac = AnalysisConfig(
        analysis_budget=config.options.analysis_budget,
        compiled_dir=compiled_dir,
        max_turns=config.options.max_turns,
        max_duration=config.options.max_duration,
        ai_model=subagent_model,
        max_files_per_agent=params.max_files_per_agent,
        time_limit=time_limit,
        deadline_at=config.options.deadline_at,
        # Carry the RunConfig + dimension so the API runner can construct a
        # per-file cache writer (synchronous cache.put on file_done='ok').
        run_config=config,
        dimension=dim_id,
    )
    n_agents = config.options.max_subagents

    # Skip scout mode for providers without per-token billing (e.g. Codex with
    # ChatGPT subscription).  Launch all agents immediately for faster results.
    ai_cmd = get_ai_cmd()
    use_scout = ai_cmd not in _NON_SCOUT_PROVIDERS

    pool = SubagentPool(
        paths=PoolPaths(work_dir=config.src, evidence_dir=params.evidence_dir, queue_path=params.queue_path,
                        src=config.src, all_files=params.all_files, standards_dir=config.standards_dir),
        options=PoolOptions(
            n_agents=n_agents,
            prompt=params.prompt,
            dimension=dim_id,
            scout_first=use_scout,
        ),
        config=base_ac,
    )
    return pool, pool.run()


def _collect_all_evidence(results: list[Any], cleanup_stream_fn: Any) -> int:
    """Sum files-read counts across all subagent result stream files, cleaning up each."""
    total = 0
    for r in results:
        if r.stream_file.exists():
            total += count_files_from_stream(r.stream_file)
            cleanup_stream_fn(r.stream_file)
    return total
