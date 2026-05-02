"""Worker logic: building agent configs and running single subagents."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.subagents._pool_models import (
    SubagentResult,
    _AGENT_ID_PREFIX,
    _DEFAULT_MAX_DURATION_S,
)
from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError, run_analysis
from quodeq.shared.logging import log_warning


@dataclass
class WorkerContext:
    """Grouped dimension and path context for a pool worker."""

    dimension: str
    dimension_key: str
    evidence_dir: Path
    queue_path: Path


def build_agent_config(
    idx: int,
    base_config: AnalysisConfig,
    wctx: WorkerContext,
) -> tuple[AnalysisConfig, Path, Path]:
    """Build per-agent AnalysisConfig, JSONL path, and stream path."""
    agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
    jsonl_file = wctx.evidence_dir / f"{wctx.dimension_key}_evidence.jsonl"
    stream_file = wctx.evidence_dir / f"{wctx.dimension_key}_{agent_id}.stream"
    bc = base_config
    agent_dur = bc.max_duration or _DEFAULT_MAX_DURATION_S
    # Clamp to remaining budget so the last in-flight agent dies on or
    # before the run-level deadline. Without this, a respawn near the
    # deadline gets a fresh full-length cap and extends the run.
    if bc.deadline_at is not None:
        import time as _time
        remaining = max(1, int(bc.deadline_at - _time.monotonic()))
        agent_dur = min(agent_dur, remaining)
    elif bc.pool_budget and bc.pool_budget > 0:
        # Legacy clamp: kept for runs without a deadline. A later task will
        # retire pool_budget entirely.
        agent_dur = min(agent_dur, bc.pool_budget)
    ac = AnalysisConfig(
        jsonl_file=jsonl_file, analysis_budget=bc.analysis_budget,
        heartbeat_interval=bc.heartbeat_interval, heartbeat_callback=bc.heartbeat_callback,
        ai_cmd=bc.ai_cmd, ai_model=bc.ai_model, max_turns=bc.max_turns,
        max_duration=agent_dur,
        compiled_dir=bc.compiled_dir, dimension=wctx.dimension,
        queue_path=wctx.queue_path, agent_id=agent_id,
        max_files_per_agent=bc.max_files_per_agent,
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
    agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
    ac, jsonl_file, stream_file = build_agent_config(idx, base_config, wctx)
    try:
        run_analysis(
            work_dir=work_dir,
            prompt=prompt,
            stream_file=stream_file,
            config=ac,
        )
        return SubagentResult(
            agent_id=agent_id, jsonl_file=jsonl_file,
            stream_file=stream_file, success=True,
        )
    except AnalysisError as exc:
        log_warning(f"Subagent {agent_id} failed: {exc}")
        return SubagentResult(
            agent_id=agent_id, jsonl_file=jsonl_file,
            stream_file=stream_file, success=False, error=str(exc),
        )
