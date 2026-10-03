"""Worker logic: building agent configs and running single subagents."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis.subagents._pool_models import (
    SubagentResult,
    agent_id_for,
    agent_stream_file,
    DEFAULT_MAX_DURATION_S,
)
from quodeq.analysis.errors import REASON_PROVIDER_FATAL, FatalProviderError
from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError, run_analysis
from quodeq.shared import cancellation
from quodeq.shared.logging import log_warning


@dataclass
class WorkerContext:
    """Grouped dimension and path context for a pool worker."""

    dimension: str
    dimension_key: str
    evidence_dir: Path
    queue_path: Path
    # None = production default (``run_analysis``, looked up at call time
    # so ``patch("...run_analysis")`` in existing tests keeps working).
    run_fn: Callable[..., Any] | None = None


def build_agent_config(
    idx: int,
    base_config: AnalysisConfig,
    wctx: WorkerContext,
) -> tuple[AnalysisConfig, Path, Path]:
    """Derive agent *idx*'s config from the pool's *base_config* and *wctx*.

    Args:
        idx: The agent's position in the pool; it names the agent and its
            stream file, so two live agents never write the same one.
        base_config: The dimension-wide config every agent starts from.
        wctx: The dimension and the directories this pool writes into.

    Returns:
        The agent's AnalysisConfig, the shared per-dimension evidence JSONL
        every agent in the pool appends to, and this agent's own stream file.
    """
    agent_id = agent_id_for(idx)
    jsonl_file = wctx.evidence_dir / f"{wctx.dimension_key}_evidence.jsonl"
    stream_file = agent_stream_file(wctx.evidence_dir, wctx.dimension_key, agent_id)
    bc = base_config
    agent_dur = bc.max_duration or DEFAULT_MAX_DURATION_S
    # Clamp to remaining budget so the last in-flight agent dies on or
    # before the run-level deadline. Without this, a respawn near the
    # deadline gets a fresh full-length cap and extends the run.
    if bc.deadline_at is not None:
        remaining = max(1, int(bc.deadline_at - time.monotonic()))
        agent_dur = min(agent_dur, remaining)
    elif bc.time_limit and bc.time_limit > 0:
        # Legacy clamp, kept for runs that carry a time limit but no
        # deadline (the API entry points and older callers).
        agent_dur = min(agent_dur, bc.time_limit)
    ac = AnalysisConfig(
        jsonl_file=jsonl_file, analysis_budget=bc.analysis_budget,
        heartbeat_interval=bc.heartbeat_interval, heartbeat_callback=bc.heartbeat_callback,
        ai_cmd=bc.ai_cmd, ai_model=bc.ai_model, max_turns=bc.max_turns,
        ai_cmd_path=bc.ai_cmd_path, cache_root=bc.cache_root,
        max_duration=agent_dur,
        compiled_dir=bc.compiled_dir, dimension=wctx.dimension,
        queue_path=wctx.queue_path, agent_id=agent_id,
        max_files_per_agent=bc.max_files_per_agent,
        # Propagate the RunConfig carrier so the API runner can wire a
        # synchronous cache writer into FindingsRouter.
        run_config=bc.run_config,
        # Propagate the run's owners directly too, so a consumer that reads
        # the AnalysisConfig field first (rather than through run_config)
        # still resolves to the same run-shared instance.
        drop_counter=bc.drop_counter,
        mcp_registry=bc.mcp_registry,
    )
    return ac, jsonl_file, stream_file


def run_single_agent(
    idx: int,
    work_dir: Path,
    prompt: str,
    base_config: AnalysisConfig,
    wctx: WorkerContext,
) -> SubagentResult:
    """Run a single subagent. Returns SubagentResult."""
    agent_id = agent_id_for(idx)
    ac, jsonl_file, stream_file = build_agent_config(idx, base_config, wctx)
    run_fn = wctx.run_fn if wctx.run_fn is not None else run_analysis

    def failed(exc: Exception) -> SubagentResult:
        return SubagentResult(
            agent_id=agent_id, jsonl_file=jsonl_file,
            stream_file=stream_file, success=False, error=str(exc),
        )

    try:
        run_fn(
            work_dir=work_dir,
            prompt=prompt,
            stream_file=stream_file,
            config=ac,
        )
        return SubagentResult(
            agent_id=agent_id, jsonl_file=jsonl_file,
            stream_file=stream_file, success=True,
        )
    except FatalProviderError as exc:
        # No retry can succeed (quota/auth/billing): cancel the whole run so
        # the spawn gate and the dimension loops stop instead of respawning
        # agents that will all die the same way.
        log_warning(
            f"Subagent {agent_id} hit a fatal provider error ({exc.reason}): {exc} "
            f"-- cancelling run, no further agents will be spawned"
        )
        cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:{exc.reason}: {exc}")
        return failed(exc)
    except AnalysisError as exc:
        log_warning(f"Subagent {agent_id} failed: {exc}")
        return failed(exc)
