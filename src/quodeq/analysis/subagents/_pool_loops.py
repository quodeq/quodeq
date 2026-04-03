"""Event loops for the subagent pool: scout-then-scale and immediate launch."""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from quodeq.analysis.subagents._pool_models import (
    ScaleUpState,
    SubagentResult,
    _FUTURE_POLL_INTERVAL_S,
    _SCOUT_TIMEOUT_S,
)
from quodeq.analysis.subagents._pool_scaling import (
    collect_done,
    maybe_scale_up,
    should_respawn,
)
from quodeq.analysis.subagents.file_queue import WorkQueue


def scout_loop(
    futures: dict[Future[SubagentResult], int],
    finished: dict[str, bool],
    results: list[SubagentResult],
    max_duration: float,
    pool_start: float,
    n_agents: int,
    max_files_per_agent: int | None,
    queue: WorkQueue | None,
    queue_path: Path,
    shared_jsonl_path: Path,
    evidence_dir: Path,
    dimension_key: str,
    submit_fn: Callable[[], None],
) -> None:
    """Run scout-then-scale loop: launch one agent, scale up when it finishes."""
    scout_timeout = min(_SCOUT_TIMEOUT_S, max_duration / max(n_agents, 1) * 0.5)
    state = ScaleUpState(
        pool_start=pool_start, max_duration=max_duration, scout_timeout=scout_timeout,
    )
    submit_fn()
    while futures:
        done = collect_done(
            futures, finished, results, shared_jsonl_path, evidence_dir, dimension_key,
        )
        state.scout_done = maybe_scale_up(
            done, state, n_agents, max_files_per_agent, queue, queue_path, submit_fn,
        )
        if not done:
            time.sleep(_FUTURE_POLL_INTERVAL_S)
            continue
        if state.scout_done:
            for _ in done:
                if should_respawn(queue, queue_path, pool_start, max_duration):
                    submit_fn()


def immediate_loop(
    futures: dict[Future[SubagentResult], int],
    finished: dict[str, bool],
    results: list[SubagentResult],
    max_duration: float,
    pool_start: float,
    n_agents: int,
    queue: WorkQueue | None,
    queue_path: Path,
    shared_jsonl_path: Path,
    evidence_dir: Path,
    dimension_key: str,
    submit_fn: Callable[[], None],
) -> None:
    """Launch all agents immediately, respawning as they complete."""
    for _ in range(n_agents):
        submit_fn()
    while futures:
        done = collect_done(
            futures, finished, results, shared_jsonl_path, evidence_dir, dimension_key,
        )
        if not done:
            time.sleep(_FUTURE_POLL_INTERVAL_S)
            continue
        for _ in done:
            if should_respawn(queue, queue_path, pool_start, max_duration):
                submit_fn()
