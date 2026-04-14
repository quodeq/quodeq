"""Event loops for the subagent pool: scout-then-scale and immediate launch."""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from quodeq.analysis.subagents._pool_models import (
    ScaleUpState,
    SubagentResult,
    _FUTURE_POLL_INTERVAL_S,
    _SCOUT_TIMEOUT_S,
)
from quodeq.analysis.subagents._pool_scaling import (
    EvidencePaths,
    ScaleUpContext,
    collect_done,
    maybe_scale_up,
    should_respawn,
)
from quodeq.analysis.subagents.file_queue import WorkQueue
from quodeq.shared.logging import log_warning as _log_warn

_SCOUT_BUDGET_FRACTION = 0.5


@dataclass
class LoopContext:
    """Grouped parameters shared by scout_loop and immediate_loop."""

    futures: dict[Future[SubagentResult], int]
    finished: dict[str, bool]
    results: list[SubagentResult]
    max_duration: float
    pool_start: float
    n_agents: int
    queue: WorkQueue | None
    queue_path: Path
    shared_jsonl_path: Path
    evidence_dir: Path
    dimension_key: str
    submit_fn: Callable[[], None]
    max_files_per_agent: int | None = None


def scout_loop(ctx: LoopContext) -> None:
    """Run scout-then-scale loop: launch one agent, scale up when it finishes."""
    scout_timeout = _SCOUT_TIMEOUT_S if ctx.max_duration <= 0 else min(_SCOUT_TIMEOUT_S, ctx.max_duration / max(ctx.n_agents, 1) * _SCOUT_BUDGET_FRACTION)
    state = ScaleUpState(
        pool_start=ctx.pool_start, max_duration=ctx.max_duration, scout_timeout=scout_timeout,
    )
    ev_paths = EvidencePaths(ctx.shared_jsonl_path, ctx.evidence_dir, ctx.dimension_key)
    ctx.submit_fn()
    while ctx.futures:
        done = collect_done(ctx.futures, ctx.finished, ctx.results, ev_paths)
        scale_ctx = ScaleUpContext(ctx.queue, ctx.queue_path, ctx.submit_fn)
        state.scout_done = maybe_scale_up(
            done, state, ctx.n_agents, ctx.max_files_per_agent,
            scale_ctx,
        )
        if not done:
            time.sleep(_FUTURE_POLL_INTERVAL_S)
            continue
        if state.scout_done:
            for _ in done:
                if should_respawn(ctx.queue, ctx.queue_path, ctx.pool_start, ctx.max_duration):
                    ctx.submit_fn()


def immediate_loop(ctx: LoopContext) -> None:
    """Launch all agents immediately, respawning as they complete."""
    ev_paths = EvidencePaths(ctx.shared_jsonl_path, ctx.evidence_dir, ctx.dimension_key)
    for _ in range(ctx.n_agents):
        ctx.submit_fn()
    while ctx.futures:
        # Check pool budget — cancel all running agents if exceeded
        if ctx.max_duration > 0:
            elapsed = time.monotonic() - ctx.pool_start
            if elapsed >= ctx.max_duration:
                _log_warn(
                    f"  Pool budget ({ctx.max_duration:.0f}s) exceeded "
                    f"-- cancelling {len(ctx.futures)} remaining agents"
                )
                for future in list(ctx.futures):
                    future.cancel()
                break
        done = collect_done(ctx.futures, ctx.finished, ctx.results, ev_paths)
        if not done:
            time.sleep(_FUTURE_POLL_INTERVAL_S)
            continue
        for _ in done:
            if should_respawn(ctx.queue, ctx.queue_path, ctx.pool_start, ctx.max_duration):
                ctx.submit_fn()
