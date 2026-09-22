"""Event loops for the subagent pool: scout-then-scale and immediate launch."""
from __future__ import annotations

import time
from concurrent.futures import Future
from dataclasses import dataclass
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
    check_agent_failure_streak,
    collect_done,
    compute_scale_up,
    maybe_scale_up,
    should_respawn,
)
from quodeq.analysis.subagents.file_queue import WorkQueue
from quodeq.shared import cancellation

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
    deadline_at: float | None = None
    # Injectable cancellation check; the default binds the process-wide
    # signal here (the composition seam) so the loops never touch the
    # singleton themselves and tests can pass an isolated callable.
    is_cancelled: Callable[[], bool] = cancellation.is_cancelled


def _respawn_for_surplus(ctx: LoopContext, just_done: int) -> None:
    """Submit one agent per pending file no in-flight agent will take.

    Agents still in flight take from the same pending set, so only the
    surplus needs a fresh slot -- and only the *just_done* slots that were
    vacated this poll are free to fill.
    """
    remaining = should_respawn(
        ctx.queue, ctx.queue_path, ctx.pool_start, ctx.max_duration,
        deadline_at=ctx.deadline_at,
    )
    for _ in range(compute_scale_up(remaining - len(ctx.futures), just_done)):
        ctx.submit_fn()


def scout_loop(ctx: LoopContext) -> None:
    """Scout-then-scale loop: one agent first, then fill the pool when the
    scout finishes or times out. Each later poll respawns for the pending
    files no in-flight agent will take, capped by the slots just vacated."""
    scout_timeout = _SCOUT_TIMEOUT_S if ctx.max_duration <= 0 else min(_SCOUT_TIMEOUT_S, ctx.max_duration / max(ctx.n_agents, 1) * _SCOUT_BUDGET_FRACTION)
    state = ScaleUpState(
        pool_start=ctx.pool_start, max_duration=ctx.max_duration, scout_timeout=scout_timeout,
    )
    ev_paths = EvidencePaths(ctx.shared_jsonl_path, ctx.evidence_dir, ctx.dimension_key)
    if ctx.is_cancelled():
        return
    ctx.submit_fn()
    while ctx.futures:
        done = collect_done(ctx.futures, ctx.finished, ctx.results, ev_paths)
        if done:
            check_agent_failure_streak(ctx.results)
        scale_ctx = ScaleUpContext(
            ctx.queue, ctx.queue_path, ctx.submit_fn,
            deadline_at=ctx.deadline_at,
        )
        gate_was_open = state.scout_done
        state.scout_done = maybe_scale_up(
            done, state, ctx.n_agents, scale_ctx, running=len(ctx.futures),
        )
        if not done:
            time.sleep(_FUTURE_POLL_INTERVAL_S)
            continue
        if not gate_was_open:
            # The scout finishing is what opened the gate this iteration, and
            # the scale-up sized itself from the free slots, the scout's own
            # included. Respawning for it on top would launch one agent more
            # than there are files left.
            continue
        _respawn_for_surplus(ctx, len(done))


def immediate_loop(ctx: LoopContext) -> None:
    """Launch all agents immediately, respawning as they complete."""
    ev_paths = EvidencePaths(ctx.shared_jsonl_path, ctx.evidence_dir, ctx.dimension_key)
    if ctx.is_cancelled():
        return
    for _ in range(ctx.n_agents):
        ctx.submit_fn()
    while ctx.futures:
        # No deadline-kill here: Future.cancel() is a no-op for running
        # threads. Enforcement is the spawn-gate in should_respawn() plus
        # the per-agent max_duration clamp set in build_agent_config().
        done = collect_done(ctx.futures, ctx.finished, ctx.results, ev_paths)
        if done:
            check_agent_failure_streak(ctx.results)
        if not done:
            time.sleep(_FUTURE_POLL_INTERVAL_S)
            continue
        _respawn_for_surplus(ctx, len(done))
