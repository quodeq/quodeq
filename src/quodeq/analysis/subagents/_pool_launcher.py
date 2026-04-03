"""Pool creation, launching, and stream-level evidence collection."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis._types import RunConfig
from quodeq.analysis.subprocess import AnalysisConfig, count_files_from_stream
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET

_MAX_FILES_PER_AGENT = 30
_MAX_FILES_PER_AGENT_CAP = 50


def _compute_files_per_agent(total_files: int) -> int:
    """Compute adaptive max files per agent. Capped to avoid turn limits."""
    return min(total_files, _MAX_FILES_PER_AGENT_CAP) if total_files > 0 else 0


def _default_subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override, or None to use the client's default."""
    return (env or os.environ).get("QUODEQ_SUBAGENT_MODEL") or None


@dataclass
class LaunchPoolParams:
    """Grouped parameters for launching a subagent pool."""
    evidence_dir: Path
    queue_path: Path
    prompt: str
    max_files_per_agent: int = _MAX_FILES_PER_AGENT


def _launch_pool(
    config: RunConfig, dim_id: str, params: LaunchPoolParams,
) -> tuple[Any, list[Any]]:
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


def _collect_all_evidence(results: list[Any], cleanup_stream_fn: Any) -> int:
    """Sum files-read counts across all subagent result stream files, cleaning up each."""
    total = 0
    for r in results:
        if r.stream_file.exists():
            total += count_files_from_stream(r.stream_file)
            cleanup_stream_fn(r.stream_file)
    return total
