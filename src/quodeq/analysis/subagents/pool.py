"""SubagentPool -- launches N parallel AI CLI subprocesses sharing a FileQueue."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from math import ceil
from pathlib import Path

from quodeq.analysis.subagents._heartbeat import HeartbeatContext, heartbeat_loop
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl, merge_jsonl
from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError, run_analysis
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET
from quodeq.shared.logging import log_info, log_warning

_AGENT_ID_PREFIX = "agent"
_FUTURE_POLL_INTERVAL_S = 0.5
_HEARTBEAT_JOIN_TIMEOUT_S = 2
_SCOUT_TIMEOUT_S = 180  # 3 minutes before forcing scale-up
_DEFAULT_MAX_DURATION_S = 1800
_DEFAULT_FILES_PER_AGENT = 30


@dataclass
class ScaleUpState:
    """Grouped parameters for scale-up decision logic."""
    pool_start: float
    max_duration: float
    scout_timeout: float
    scout_done: bool = False


@dataclass
class PoolPaths:
    """Grouped filesystem paths for the subagent pool."""
    work_dir: Path
    evidence_dir: Path
    queue_path: Path


@dataclass
class PoolOptions:
    """Grouped behavioral configuration for the subagent pool."""
    n_agents: int
    prompt: str
    dimension: str | list[str]
    scout_first: bool = True


@dataclass
class SubagentResult:
    """Result from a single subagent run."""
    agent_id: str
    jsonl_file: Path
    stream_file: Path
    success: bool
    error: str = ""


class SubagentPool:
    """Manages N parallel AI CLI subprocesses sharing a FileQueue."""

    def __init__(
        self,
        paths: PoolPaths,
        options: PoolOptions,
        config: AnalysisConfig | None = None,
    ):
        self._n = max(1, options.n_agents)
        self._work_dir, self._prompt = paths.work_dir, options.prompt
        self._evidence_dir, self._queue_path = paths.evidence_dir, paths.queue_path
        dimension = options.dimension
        if isinstance(dimension, list):
            self._dimensions, self._dimension = dimension, ",".join(dimension)
            self._dimension_key = "consolidated"
        else:
            self._dimensions = [dimension] if dimension else []
            self._dimension, self._dimension_key = dimension, dimension
        self._base_config = config or AnalysisConfig()
        self._scout_first, self._jsonl_lock = options.scout_first, threading.Lock()
        self._futures: dict[Future[SubagentResult], int] = {}
        self._finished: dict[str, bool] = {}
        self._next_idx = 0

    def _shared_jsonl_path(self) -> Path:
        """The shared JSONL path all agents write to (same path the UI expects)."""
        return self._evidence_dir / f"{self._dimension_key}_evidence.jsonl"

    def _build_agent_config(self, idx: int) -> tuple[AnalysisConfig, Path, Path]:
        """Build per-agent AnalysisConfig, JSONL path, and stream path."""
        agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
        jsonl_file = self._shared_jsonl_path()
        stream_file = self._evidence_dir / f"{self._dimension_key}_{agent_id}.stream"
        bc = self._base_config
        ac = AnalysisConfig(
            jsonl_file=jsonl_file, analysis_budget=bc.analysis_budget,
            heartbeat_interval=bc.heartbeat_interval, heartbeat_callback=bc.heartbeat_callback,
            ai_cmd=bc.ai_cmd, ai_model=bc.ai_model, max_turns=bc.max_turns,
            max_duration=bc.max_duration or _DEFAULT_MAX_DURATION_S,
            compiled_dir=bc.compiled_dir, dimension=self._dimension,
            queue_path=self._queue_path, agent_id=agent_id,
            max_files_per_agent=bc.max_files_per_agent,
        )
        return ac, jsonl_file, stream_file

    def _run_single(self, idx: int) -> SubagentResult:
        """Run a single subagent. Returns SubagentResult."""
        agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
        ac, jsonl_file, stream_file = self._build_agent_config(idx)
        try:
            run_analysis(
                work_dir=self._work_dir,
                prompt=self._prompt,
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

    def _should_respawn(self, pool_start: float, max_duration: float) -> int:
        """Return remaining file count if a new agent should be spawned, else 0."""
        remaining = FileQueue(self._queue_path).remaining()
        elapsed = time.monotonic() - pool_start
        if elapsed >= max_duration:
            if remaining > 0:
                log_warning(
                    f"  Pool time limit ({max_duration}s) reached -- "
                    f"{remaining} files left, not spawning new agents"
                )
            return 0
        return remaining

    def _compute_scale_up(self, remaining: int) -> int:
        """Compute how many overflow agents to spawn after scout completes."""
        if remaining <= 0:
            return 0
        needed = ceil(remaining / (self._base_config.max_files_per_agent or _DEFAULT_FILES_PER_AGENT))
        return min(needed, self._n - 1) if needed > 1 else 0

    def _collect_done(
        self, results: list[SubagentResult],
    ) -> set[Future[SubagentResult]]:
        """Collect completed futures, updating results and finished map."""
        done_futures = {f for f in self._futures if f.done()}
        for future in done_futures:
            idx = self._futures[future]
            agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
            try:
                result = future.result()
            except (OSError, RuntimeError, ValueError) as exc:
                log_warning(f"  {agent_id} raised {type(exc).__name__}: {exc}")
                result = SubagentResult(
                    agent_id=agent_id,
                    jsonl_file=self._shared_jsonl_path(),
                    stream_file=self._evidence_dir / f"{self._dimension_key}_{agent_id}.stream",
                    success=False,
                    error=str(exc),
                )
            self._finished[result.agent_id] = True
            results.append(result)
            del self._futures[future]
        return done_futures

    def _process_completed_futures(
        self, done: set, pool_start: float, max_duration: float, executor: ThreadPoolExecutor,
    ) -> None:
        """Respawn agents for each completed future if queue still has files."""
        for _ in done:
            if self._should_respawn(pool_start, max_duration):
                self._submit_agent(executor)

    def _start_heartbeat(self) -> tuple[threading.Event, threading.Thread]:
        """Create and start the heartbeat monitoring thread."""
        stop = threading.Event()
        ctx = HeartbeatContext(
            queue_path=self._queue_path, dimension_key=self._dimension_key,
            jsonl_path=self._shared_jsonl_path(), lock=self._jsonl_lock,
        )
        heartbeat = threading.Thread(
            target=heartbeat_loop,
            args=(stop, self._finished, ctx),
            daemon=True,
        )
        heartbeat.start()
        return stop, heartbeat

    def _submit_agent(self, executor: ThreadPoolExecutor) -> None:
        """Submit a new agent to the executor."""
        self._finished[f"{_AGENT_ID_PREFIX}-{self._next_idx}"] = False
        self._futures[executor.submit(self._run_single, self._next_idx)] = self._next_idx
        self._next_idx += 1

    def _maybe_scale_up(
        self, done: set, state: ScaleUpState, executor: ThreadPoolExecutor,
    ) -> bool:
        """Check if scout phase is complete and scale up if needed. Returns updated scout_done."""
        if state.scout_done:
            return True
        elapsed = time.monotonic() - state.pool_start
        scout_completed = len(done) > 0
        scout_timed_out = elapsed >= state.scout_timeout and self._n > 1
        if not (scout_completed or scout_timed_out):
            return False
        remaining = self._should_respawn(state.pool_start, state.max_duration)
        for _ in range(self._compute_scale_up(remaining)):
            self._submit_agent(executor)
        return True

    def _scout_loop(
        self, results: list[SubagentResult], max_duration: float, pool_start: float,
        executor: ThreadPoolExecutor,
    ) -> None:
        """Run scout-then-scale loop inside an executor."""
        scout_timeout = min(_SCOUT_TIMEOUT_S, max_duration / max(self._n, 1) * 0.5)
        scale_state = ScaleUpState(pool_start=pool_start, max_duration=max_duration, scout_timeout=scout_timeout)
        self._submit_agent(executor)

        while self._futures:
            done = self._collect_done(results)
            scale_state.scout_done = self._maybe_scale_up(done, scale_state, executor)
            if not done:
                time.sleep(_FUTURE_POLL_INTERVAL_S)
                continue
            if scale_state.scout_done:
                self._process_completed_futures(done, pool_start, max_duration, executor)

    def _immediate_loop(
        self, results: list[SubagentResult], max_duration: float, pool_start: float,
        executor: ThreadPoolExecutor,
    ) -> None:
        """Run all agents immediately inside an executor."""
        for _ in range(self._n):
            self._submit_agent(executor)
        while self._futures:
            done = self._collect_done(results)
            if not done:
                time.sleep(_FUTURE_POLL_INTERVAL_S)
                continue
            self._process_completed_futures(done, pool_start, max_duration, executor)

    def _run_pool_loop(
        self, results: list[SubagentResult], max_duration: float, pool_start: float,
    ) -> None:
        """Execute the pool loop: scout-then-scale or immediate launch."""
        with ThreadPoolExecutor(max_workers=self._n) as pool:
            if self._scout_first:
                self._scout_loop(results, max_duration, pool_start, pool)
            else:
                self._immediate_loop(results, max_duration, pool_start, pool)

    def run(self) -> list[SubagentResult]:
        """Launch agents in parallel, returning a SubagentResult per agent."""
        max_duration = self._base_config.pool_budget or _DEFAULT_POOL_BUDGET
        if self._scout_first:
            log_info(f"Launching scout agent for {self._dimension_key} (max {self._n} agents)")
        else:
            log_info(f"Launching {self._n} agents for {self._dimension_key}")
        results: list[SubagentResult] = []
        self._finished.clear()
        self._futures.clear()
        self._next_idx = 0

        stop, heartbeat = self._start_heartbeat()
        try:
            self._run_pool_loop(results, max_duration, time.monotonic())
        finally:
            stop.set()
            heartbeat.join(timeout=_HEARTBEAT_JOIN_TIMEOUT_S)

        succeeded = sum(1 for r in results if r.success)
        log_info(f"Subagent pool done: {succeeded}/{self._next_idx} agents ran, {succeeded} succeeded")
        return results

    @staticmethod
    def deduplicate_jsonl(jsonl_path: Path) -> int:
        """Deduplicate a shared JSONL file in-place by (p, file, line, t)."""
        return deduplicate_jsonl(jsonl_path)

    @staticmethod
    def merge_jsonl(results: list[SubagentResult], output: Path) -> Path:
        """Merge JSONL files from all agents, deduplicating by (p, file, line, t)."""
        return merge_jsonl((r.jsonl_file for r in results), output)
