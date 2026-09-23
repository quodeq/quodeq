"""Scaling logic: respawn decisions, scale-up computation, future collection."""
from __future__ import annotations

import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.analysis.subagents._pool_models import (
    ScaleUpState,
    SubagentResult,
    _AGENT_ID_PREFIX,
)
from quodeq.analysis.errors import REASON_AGENT_FAILURE_STREAK
from quodeq.analysis.subagents.file_queue import FileQueue, WorkQueue
from quodeq.config.analysis_env import agent_failure_streak_limit
from quodeq.shared import cancellation
from quodeq.shared.logging import log_warning


@dataclass
class ScaleUpContext:
    """Grouped parameters for scale-up decisions."""

    queue: WorkQueue | None
    queue_path: Path
    submit_fn: Callable[[], None]
    deadline_at: float | None = None
    run_deadline_at: float | None = None


@dataclass
class EvidencePaths:
    """Grouped paths for evidence collection."""

    shared_jsonl_path: Path
    evidence_dir: Path
    dimension_key: str


_QUEUE_CACHE_MAX_SIZE = 64
_cached_file_queues: OrderedDict[Path, WorkQueue] = OrderedDict()


def clear_cached_queues() -> None:
    """Empty the process-wide FileQueue cache (test isolation hook)."""
    _cached_file_queues.clear()


def get_queue(
    queue: WorkQueue | None, queue_path: Path,
    *, cache: OrderedDict[Path, WorkQueue] | None = None,
) -> WorkQueue:
    """Return the injected queue or construct a FileQueue from the path.

    When *queue* is None a ``FileQueue`` is constructed from *queue_path*.
    The result is cached by path so repeated calls avoid rebuilding the queue.
    The cache is bounded (LRU): in long-running sessions that touch many
    distinct queue paths, the oldest entry is evicted once the cap is hit.
    *cache* defaults to the process-wide cache; tests inject their own so
    cached queues never leak between them.
    """
    if queue is not None:
        return queue
    c = cache if cache is not None else _cached_file_queues
    cached = c.get(queue_path)
    if cached is not None:
        c.move_to_end(queue_path)
        return cached
    fq: WorkQueue = FileQueue(queue_path)
    c[queue_path] = fq
    if len(c) > _QUEUE_CACHE_MAX_SIZE:
        c.popitem(last=False)
    return fq


def should_respawn(
    queue: WorkQueue | None, queue_path: Path,
    pool_start: float, max_duration: float,
    *, deadline_at: float | None = None, run_deadline_at: float | None = None,
) -> int:
    """Return remaining file count if a new agent should be spawned, else 0.

    Spawning is gated by two ceilings:
    - the pool-local *max_duration* (elapsed since *pool_start*), and
    - *deadline_at*, a monotonic wall-clock from the run config: the run
      deadline, or one dimension's slice of it when *run_deadline_at* (the
      whole-run deadline) is later.

    Without the deadline gate, agents whose per-agent budget was clamped to
    "remaining run budget" (1s past the deadline) would die and immediately
    be respawned, producing an infinite stream of 1-second agents that never
    do useful work.
    """
    remaining = get_queue(queue, queue_path).remaining()
    if cancellation.is_cancelled():
        if remaining > 0:
            log_warning(
                f"  Run cancelled -- {remaining} files left, "
                f"not spawning new agents"
            )
        return 0
    if deadline_at is not None and time.monotonic() >= deadline_at:
        if remaining > 0:
            sliced = run_deadline_at is not None and deadline_at < run_deadline_at
            budget = "dimension slice" if sliced else "run deadline"
            log_warning(
                f"  Time budget reached ({budget}) -- {remaining} files left, "
                f"not spawning new agents"
            )
        return 0
    if max_duration <= 0:
        return remaining  # 0 = unlimited
    elapsed = time.monotonic() - pool_start
    if elapsed >= max_duration:
        if remaining > 0:
            log_warning(
                f"  Pool time limit ({max_duration}s) reached -- "
                f"{remaining} files left, not spawning new agents"
            )
        return 0
    return remaining


def _agent_failure_streak_limit(env: dict[str, str] | None = None) -> int:
    """Consecutive whole-agent failures tolerated before the run is cancelled.

    Env override QUODEQ_AGENT_FAILURE_STREAK (resolved by the config layer);
    0 disables the backstop.
    """
    return agent_failure_streak_limit(env)


def check_agent_failure_streak(results: list[SubagentResult]) -> None:
    """Cancel the run when every recent agent died without a single success.

    Provider-agnostic backstop for failure modes the fatal-error
    classification doesn't recognize: N consecutive dead agents means the
    provider cannot serve this run, and respawning only burns wall-clock and
    spams the console. Cancellation is enforced by the spawn gate
    (``should_respawn``) and the dimension loops.
    """
    limit = _agent_failure_streak_limit()
    if limit <= 0 or cancellation.is_cancelled():
        return
    streak = 0
    for result in reversed(results):
        if result.success:
            break
        streak += 1
    if streak >= limit:
        last_error = results[-1].error or "unknown error"
        log_warning(
            f"  {streak} consecutive subagent failures (last: {last_error}) "
            f"-- cancelling run, provider appears unable to serve requests. "
            f"Adjust with QUODEQ_AGENT_FAILURE_STREAK (0 disables)."
        )
        cancellation.request_cancel(reason=REASON_AGENT_FAILURE_STREAK)


def compute_scale_up(remaining: int, free_slots: int) -> int:
    """Agents to launch when the scout gate opens: every free slot the
    queue can still feed. No files-per-agent estimate; a slot launched for
    a file that another agent takes first exits on its empty take (one
    turn for a CLI agent, nothing for the API runner)."""
    return max(0, min(remaining, free_slots))


def collect_done(
    futures: dict[Future[SubagentResult], int],
    finished: dict[str, bool],
    results: list[SubagentResult],
    paths: EvidencePaths,
) -> set[Future[SubagentResult]]:
    """Collect completed futures, updating results and finished map."""
    done_futures = {f for f in futures if f.done()}
    for future in done_futures:
        idx = futures[future]
        agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
        try:
            result = future.result()
        except (OSError, RuntimeError, ValueError) as exc:
            log_warning(f"  {agent_id} raised {type(exc).__name__}: {exc}")
            result = SubagentResult(
                agent_id=agent_id,
                jsonl_file=paths.shared_jsonl_path,
                stream_file=paths.evidence_dir / f"{paths.dimension_key}_{agent_id}.stream",
                success=False,
                error=str(exc),
            )
        finished[result.agent_id] = True
        results.append(result)
        del futures[future]
    return done_futures


def maybe_scale_up(
    done: set, state: ScaleUpState, n_agents: int, ctx: ScaleUpContext,
    *, running: int,
) -> bool:
    """Open the scout gate and fill the pool. Returns the updated scout_done.

    The scout is one agent sent ahead to surface entry problems (auth,
    quota, oversized prompt) before the run commits to *n_agents*. The gate
    opens when its future resolves, whatever the outcome, or after the
    scout timeout while it is still running. A fatal provider error cancels
    the run from the worker thread before the future resolves, so
    ``should_respawn`` then reports nothing left and no agent launches; a
    non-fatal scout failure is left to ``check_agent_failure_streak``.
    *running* is the number of agents still in flight; the free slots are
    the rest of the pool, including the scout's own slot once it finished.
    """
    if state.scout_done:
        return True
    elapsed = time.monotonic() - state.pool_start
    scout_completed = len(done) > 0
    scout_timed_out = elapsed >= state.scout_timeout and n_agents > 1
    if not (scout_completed or scout_timed_out):
        return False
    remaining = should_respawn(
        ctx.queue, ctx.queue_path, state.pool_start, state.max_duration,
        deadline_at=ctx.deadline_at, run_deadline_at=ctx.run_deadline_at,
    )
    for _ in range(compute_scale_up(remaining, n_agents - running)):
        ctx.submit_fn()
    return True
