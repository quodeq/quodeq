"""Scaling logic: respawn decisions, scale-up computation, future collection."""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Callable

from quodeq.analysis.subagents._pool_models import (
    ScaleUpState,
    SubagentResult,
    _AGENT_ID_PREFIX,
    _DEFAULT_FILES_PER_AGENT,
)
from quodeq.analysis.subagents.file_queue import FileQueue, WorkQueue
from quodeq.shared.logging import log_warning


@dataclass
class ScaleUpContext:
    """Grouped parameters for scale-up decisions."""

    queue: WorkQueue | None
    queue_path: Path
    submit_fn: Callable[[], None]


@dataclass
class EvidencePaths:
    """Grouped paths for evidence collection."""

    shared_jsonl_path: Path
    evidence_dir: Path
    dimension_key: str


_cached_file_queues: dict[Path, WorkQueue] = {}


def get_queue(queue: WorkQueue | None, queue_path: Path) -> WorkQueue:
    """Return the injected queue or construct a FileQueue from the path.

    When *queue* is None a ``FileQueue`` is constructed from *queue_path*.
    The result is cached by path so repeated calls avoid rebuilding the queue.
    """
    if queue is not None:
        return queue
    cached = _cached_file_queues.get(queue_path)
    if cached is not None:
        return cached
    fq: WorkQueue = FileQueue(queue_path)
    _cached_file_queues[queue_path] = fq
    return fq


def should_respawn(
    queue: WorkQueue | None, queue_path: Path,
    pool_start: float, max_duration: float,
) -> int:
    """Return remaining file count if a new agent should be spawned, else 0."""
    remaining = get_queue(queue, queue_path).remaining()
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


def compute_scale_up(
    remaining: int, n_agents: int, max_files_per_agent: int | None,
) -> int:
    """Compute how many overflow agents to spawn after scout completes."""
    if remaining <= 0:
        return 0
    needed = ceil(remaining / (max_files_per_agent or _DEFAULT_FILES_PER_AGENT))
    return min(needed, n_agents - 1) if needed > 1 else 0


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
    done: set, state: ScaleUpState, n_agents: int,
    max_files_per_agent: int | None,
    ctx: ScaleUpContext,
) -> bool:
    """Check if scout phase is complete and scale up if needed. Returns updated scout_done."""
    if state.scout_done:
        return True
    elapsed = time.monotonic() - state.pool_start
    scout_completed = len(done) > 0
    scout_timed_out = elapsed >= state.scout_timeout and n_agents > 1
    if not (scout_completed or scout_timed_out):
        return False
    remaining = should_respawn(ctx.queue, ctx.queue_path, state.pool_start, state.max_duration)
    for _ in range(compute_scale_up(remaining, n_agents, max_files_per_agent)):
        ctx.submit_fn()
    return True
