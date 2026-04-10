"""SubagentPool -- launches N parallel AI CLI subprocesses sharing a FileQueue."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from quodeq.analysis.subagents._heartbeat import HeartbeatContext, heartbeat_loop
from quodeq.analysis.subagents._pool_loops import LoopContext, immediate_loop, scout_loop
from quodeq.analysis.subagents._pool_models import (
    PoolOptions,
    PoolPaths,
    SubagentResult,
    _AGENT_ID_PREFIX,
    _HEARTBEAT_JOIN_TIMEOUT_S,
)
from quodeq.analysis.subagents._pool_scaling import compute_scale_up
from quodeq.analysis.subagents._pool_worker import WorkerContext, build_agent_config, run_single_agent
from quodeq.analysis.subagents.file_queue import WorkQueue
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl, merge_jsonl
from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET
from quodeq.shared.logging import log_info

# Re-export public API so existing imports keep working.
__all__ = ["SubagentPool", "SubagentResult", "PoolPaths", "PoolOptions"]


class SubagentPool:
    """Manages N parallel AI CLI subprocesses sharing a FileQueue."""

    def __init__(
        self,
        paths: PoolPaths,
        options: PoolOptions,
        config: AnalysisConfig | None = None,
        queue: WorkQueue | None = None,
    ):
        self._n = max(1, options.n_agents)
        self._paths = paths
        self._work_dir, self._prompt = paths.work_dir, options.prompt
        self._evidence_dir, self._queue_path = paths.evidence_dir, paths.queue_path
        self._queue = queue
        dimension = options.dimension
        if isinstance(dimension, list):
            self._dimensions, self._dimension = dimension, ",".join(dimension)
            self._dimension_key = "consolidated"
        else:
            self._dimensions = [dimension] if dimension else []
            self._dimension, self._dimension_key = dimension, dimension
        self._base_config = config or AnalysisConfig()
        self._worker_ctx = WorkerContext(
            dimension=self._dimension, dimension_key=self._dimension_key,
            evidence_dir=self._evidence_dir, queue_path=self._queue_path,
        )
        self._scout_first, self._jsonl_lock = options.scout_first, threading.Lock()
        self._phase = options.phase
        self._futures: dict[Future[SubagentResult], int] = {}
        self._finished: dict[str, bool] = {}
        self._next_idx = 0

    def _shared_jsonl_path(self) -> Path:
        return self._evidence_dir / f"{self._dimension_key}_evidence.jsonl"

    def _build_agent_config(self, idx: int) -> tuple[AnalysisConfig, Path, Path]:
        return build_agent_config(idx, self._base_config, self._worker_ctx)

    def _compute_scale_up(self, remaining: int) -> int:
        return compute_scale_up(remaining, self._n, self._base_config.max_files_per_agent)

    def _run_single(self, idx: int) -> SubagentResult:
        return run_single_agent(
            idx, self._work_dir, self._prompt, self._base_config,
            self._worker_ctx,
        )

    def _submit_agent(self, executor: ThreadPoolExecutor) -> None:
        self._finished[f"{_AGENT_ID_PREFIX}-{self._next_idx}"] = False
        self._futures[executor.submit(self._run_single, self._next_idx)] = self._next_idx
        self._next_idx += 1

    def _start_heartbeat(self) -> tuple[threading.Event, threading.Thread]:
        stop = threading.Event()
        ctx = HeartbeatContext(
            queue_path=self._queue_path, dimension_key=self._dimension_key,
            jsonl_path=self._shared_jsonl_path(), lock=self._jsonl_lock,
        )
        hb = threading.Thread(
            target=heartbeat_loop, args=(stop, self._finished, ctx), daemon=True,
        )
        hb.start()
        return stop, hb

    def run(self) -> list[SubagentResult]:
        """Launch agents in parallel, returning a SubagentResult per agent."""
        max_dur = self._base_config.pool_budget if self._base_config.pool_budget is not None else _DEFAULT_POOL_BUDGET
        if self._scout_first:
            log_info(f"[{self._phase}] Launching scout agent for {self._dimension_key} (max {self._n} agents)")
        else:
            log_info(f"[{self._phase}] Launching {self._n} agents for {self._dimension_key}")
        results: list[SubagentResult] = []
        self._finished.clear()
        self._futures.clear()
        self._next_idx = 0
        stop, hb = self._start_heartbeat()
        try:
            with ThreadPoolExecutor(max_workers=self._n) as pool:
                ctx = LoopContext(
                    futures=self._futures, finished=self._finished, results=results,
                    max_duration=max_dur, pool_start=time.monotonic(),
                    n_agents=self._n,
                    queue=self._queue, queue_path=self._queue_path,
                    shared_jsonl_path=self._shared_jsonl_path(),
                    evidence_dir=self._evidence_dir, dimension_key=self._dimension_key,
                    submit_fn=lambda: self._submit_agent(pool),
                    max_files_per_agent=self._base_config.max_files_per_agent,
                )
                if self._scout_first:
                    scout_loop(ctx)
                else:
                    immediate_loop(ctx)
        finally:
            stop.set()
            hb.join(timeout=_HEARTBEAT_JOIN_TIMEOUT_S)
        succeeded = sum(1 for r in results if r.success)
        log_info(f"Subagent pool done: {succeeded}/{self._next_idx} agents ran, {succeeded} succeeded")
        return results

    @staticmethod
    def deduplicate_jsonl(jsonl_path: Path) -> int:
        return deduplicate_jsonl(jsonl_path)

    @staticmethod
    def merge_jsonl(results: list[SubagentResult], output: Path) -> Path:
        return merge_jsonl((r.jsonl_file for r in results), output)
