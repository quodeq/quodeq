"""SubagentPool -- launches N parallel AI CLI subprocesses sharing a FileQueue.

Each subagent:
  - Gets its own MCP server with access to the shared queue
  - Gets its own JSONL output file and stream file
  - Uses the subagent.md prompt (file-fed, not search-based)
  - Dies when the queue is empty or max_turns is reached

The pool merges all JSONL files at the end, deduplicating by (p, file, line, t).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl, dedup_jsonl_lines, merge_jsonl
from quodeq.engine.analysis import AnalysisConfig, AnalysisError, run_analysis
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.shared.logging import log_info, log_success, log_warning
from quodeq.shared.utils import open_text

_AGENT_ID_PREFIX = "agent"
_HEARTBEAT_INTERVAL = 10
_FUTURE_POLL_INTERVAL_S = 0.5
_HEARTBEAT_JOIN_TIMEOUT_S = 2

_DEFAULT_POOL_BUDGET = 600  # 10 minutes total pool budget
_SECONDS_PER_MINUTE = 60


@dataclass
class PoolPaths:
    """Grouped filesystem paths for the subagent pool."""
    work_dir: Path
    evidence_dir: Path
    queue_path: Path


@dataclass
class SubagentResult:
    """Result from a single subagent run."""
    agent_id: str
    jsonl_file: Path
    stream_file: Path
    success: bool
    error: str = ""


class SubagentPool:
    """Manages N parallel AI CLI subprocesses sharing a FileQueue.

    Usage::

        pool = SubagentPool(
            n_agents=5,
            paths=PoolPaths(work_dir=repo_path, evidence_dir=evidence_dir, queue_path=queue_path),
            prompt=rendered_prompt,
            config=AnalysisConfig(...),
        )
        merged = pool.run()  # blocks until all agents finish
    """

    def __init__(
        self,
        n_agents: int,
        paths: PoolPaths,
        prompt: str,
        dimension: str,
        config: AnalysisConfig | None = None,
    ):
        self._n = max(1, n_agents)
        self._work_dir = paths.work_dir
        self._prompt = prompt
        self._evidence_dir = paths.evidence_dir
        self._queue_path = paths.queue_path
        self._dimension = dimension
        self._base_config = config or AnalysisConfig()
        self._jsonl_lock = threading.Lock()
        # Initialised here so helpers like _collect_done/_process_completed_futures
        # never encounter missing attributes regardless of call order.
        self._futures: dict[Future[SubagentResult], int] = {}
        self._finished: dict[str, bool] = {}
        self._next_idx = 0

    def _shared_jsonl_path(self) -> Path:
        """The shared JSONL path all agents write to (same path the UI expects)."""
        return self._evidence_dir / f"{self._dimension}_evidence.jsonl"

    def _build_agent_config(self, idx: int) -> tuple[AnalysisConfig, Path, Path]:
        """Build per-agent AnalysisConfig, JSONL path, and stream path."""
        agent_id = f"{_AGENT_ID_PREFIX}-{idx}"
        # All agents append to the same JSONL -- the UI reads this file live.
        # Writes are synchronized via self._jsonl_lock.
        jsonl_file = self._shared_jsonl_path()
        stream_file = self._evidence_dir / f"{self._dimension}_{agent_id}.stream"

        ac = AnalysisConfig(
            jsonl_file=jsonl_file,
            analysis_budget=self._base_config.analysis_budget,
            heartbeat_interval=self._base_config.heartbeat_interval,
            heartbeat_callback=self._base_config.heartbeat_callback,
            ai_cmd=self._base_config.ai_cmd,
            ai_model=self._base_config.ai_model,
            max_turns=self._base_config.max_turns,
            max_duration=None,
            compiled_dir=self._base_config.compiled_dir,
            dimension=self._dimension,
            queue_path=self._queue_path,
            agent_id=agent_id,
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

    def _count_total_findings(self) -> int:
        """Count findings in the shared JSONL file."""
        jsonl = self._shared_jsonl_path()
        try:
            if jsonl.exists():
                with self._jsonl_lock:
                    with open_text(jsonl) as f:
                        return sum(1 for line in f if line.strip())
        except OSError:
            pass
        return 0

    def _heartbeat_loop(self, stop: threading.Event, finished: dict[str, bool]) -> None:
        """Emit periodic progress lines until stopped."""
        start = time.monotonic()
        while not stop.wait(_HEARTBEAT_INTERVAL):
            try:
                elapsed = int(time.monotonic() - start)
                mins, secs = divmod(elapsed, _SECONDS_PER_MINUTE)
                findings = self._count_total_findings()
                remaining, taken = FileQueue(self._queue_path).stats()
                done = sum(1 for v in finished.values() if v)
                log_info(
                    f"  [{self._dimension}] {mins}m{secs:02d}s | "
                    f"{done}/{self._n} agents done | "
                    f"{taken} files taken ({remaining} left) | "
                    f"{findings} findings"
                )
            except (OSError, ValueError, RuntimeError) as exc:
                log_warning(f"Heartbeat error: {exc}")

    def _should_respawn(
        self, pool_start: float, max_duration: float,
    ) -> int:
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

    def _collect_done(
        self, results: list[SubagentResult],
    ) -> set[Future[SubagentResult]]:
        """Collect completed futures, updating results and finished map.

        Returns the set of completed futures.
        """
        done_futures = {f for f in self._futures if f.done()}
        for future in done_futures:
            result = future.result()
            self._finished[result.agent_id] = True
            if result.success:
                log_success(f"  {result.agent_id} finished")
            results.append(result)
            del self._futures[future]
        return done_futures

    def _process_completed_futures(
        self,
        done: set[Future[SubagentResult]],
        pool_start: float,
        max_duration: float,
        executor: ThreadPoolExecutor,
    ) -> None:
        """Respawn agents for each completed future if queue still has files."""
        for _ in done:
            remaining = self._should_respawn(pool_start, max_duration)
            if remaining:
                log_info(f"  {remaining} files left -- spawning agent-{self._next_idx}")
                self._finished[f"{_AGENT_ID_PREFIX}-{self._next_idx}"] = False
                self._futures[executor.submit(self._run_single, self._next_idx)] = self._next_idx
                self._next_idx += 1

    def _start_heartbeat(self) -> tuple[threading.Event, threading.Thread]:
        """Create and start the heartbeat monitoring thread."""
        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop, args=(stop, self._finished), daemon=True,
        )
        heartbeat.start()
        return stop, heartbeat

    def _run_pool_loop(
        self, results: list[SubagentResult], max_duration: float, pool_start: float,
    ) -> None:
        """Execute the main thread-pool loop: submit initial agents and respawn on completion."""
        with ThreadPoolExecutor(max_workers=self._n) as pool:
            for _ in range(self._n):
                self._finished[f"{_AGENT_ID_PREFIX}-{self._next_idx}"] = False
                self._futures[pool.submit(self._run_single, self._next_idx)] = self._next_idx
                self._next_idx += 1

            while self._futures:
                done = self._collect_done(results)
                if not done:
                    time.sleep(_FUTURE_POLL_INTERVAL_S)
                    continue
                self._process_completed_futures(done, pool_start, max_duration, pool)

    def run(self) -> list[SubagentResult]:
        """Launch agents in parallel, respawning when slots free up and queue has files.

        Returns list of SubagentResult (one per agent, including failures).
        """
        max_duration = self._base_config.max_duration or _DEFAULT_POOL_BUDGET
        log_info(f"Launching {self._n} subagents for {self._dimension}")
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
        """Deduplicate a shared JSONL file in-place by (p, file, line, t).

        Returns the number of unique findings kept.
        """
        return deduplicate_jsonl(jsonl_path)

    @staticmethod
    def merge_jsonl(results: list[SubagentResult], output: Path) -> Path:
        """Merge JSONL files from all agents, deduplicating by (p, file, line, t).

        Returns the output path.
        """
        return merge_jsonl((r.jsonl_file for r in results), output)
