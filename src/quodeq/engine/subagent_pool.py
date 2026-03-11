"""SubagentPool — launches N parallel AI CLI subprocesses sharing a FileQueue.

Each subagent:
  - Gets its own MCP server with access to the shared queue
  - Gets its own JSONL output file and stream file
  - Uses the subagent.md prompt (file-fed, not search-based)
  - Dies when the queue is empty or max_turns is reached

The pool merges all JSONL files at the end, deduplicating by (p, file, line, t).
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from quodeq.engine.analysis import AnalysisConfig, AnalysisError, run_analysis
from quodeq.engine.file_queue import FileQueue
from quodeq.shared.logging import log_info, log_success, log_warning

_HEARTBEAT_INTERVAL = 10

_SUBAGENT_MAX_TURNS = 40
_SUBAGENT_MAX_DURATION = 600  # 10 minutes per agent


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
            work_dir=repo_path,
            prompt=rendered_prompt,
            evidence_dir=evidence_dir,
            queue_path=queue_path,
            config=AnalysisConfig(...),
        )
        merged = pool.run()  # blocks until all agents finish
    """

    def __init__(
        self,
        n_agents: int,
        work_dir: Path,
        prompt: str,
        evidence_dir: Path,
        queue_path: Path,
        dimension: str,
        config: AnalysisConfig | None = None,
    ):
        self._n = max(1, n_agents)
        self._work_dir = work_dir
        self._prompt = prompt
        self._evidence_dir = evidence_dir
        self._queue_path = queue_path
        self._dimension = dimension
        self._base_config = config or AnalysisConfig()

    def _build_agent_config(self, idx: int) -> tuple[AnalysisConfig, Path, Path]:
        """Build per-agent AnalysisConfig, JSONL path, and stream path."""
        agent_id = f"agent-{idx}"
        jsonl_file = self._evidence_dir / f"{self._dimension}_{agent_id}.jsonl"
        stream_file = self._evidence_dir / f"{self._dimension}_{agent_id}.stream"

        ac = AnalysisConfig(
            jsonl_file=jsonl_file,
            analysis_budget=self._base_config.analysis_budget,
            heartbeat_interval=self._base_config.heartbeat_interval,
            heartbeat_callback=self._base_config.heartbeat_callback,
            ai_cmd=self._base_config.ai_cmd,
            ai_model=self._base_config.ai_model,
            max_turns=self._base_config.max_turns or _SUBAGENT_MAX_TURNS,
            max_duration=self._base_config.max_duration or _SUBAGENT_MAX_DURATION,
            compiled_dir=self._base_config.compiled_dir,
            dimension=self._dimension,
            queue_path=self._queue_path,
            agent_id=agent_id,
        )
        return ac, jsonl_file, stream_file

    def _run_single(self, idx: int) -> SubagentResult:
        """Run a single subagent. Returns SubagentResult."""
        agent_id = f"agent-{idx}"
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
        """Count total findings across all agent JSONL files."""
        total = 0
        for i in range(self._n):
            jsonl = self._evidence_dir / f"{self._dimension}_agent-{i}.jsonl"
            try:
                if jsonl.exists():
                    with open(jsonl) as f:
                        total += sum(1 for line in f if line.strip())
            except OSError:
                pass
        return total

    def _heartbeat_loop(self, stop: threading.Event, finished: dict[str, bool]) -> None:
        """Emit periodic progress lines until stopped."""
        start = time.monotonic()
        while not stop.wait(_HEARTBEAT_INTERVAL):
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, 60)
            findings = self._count_total_findings()
            queue = FileQueue(self._queue_path)
            remaining = queue.remaining()
            taken = len(queue.all_taken_files())
            done = sum(1 for v in finished.values() if v)
            log_info(
                f"  [{self._dimension}] {mins}m{secs:02d}s | "
                f"{done}/{self._n} agents done | "
                f"{taken} files taken ({remaining} left) | "
                f"{findings} findings"
            )

    def run(self) -> list[SubagentResult]:
        """Launch all agents in parallel. Blocks until all complete.

        Returns list of SubagentResult (one per agent, including failures).
        """
        log_info(f"Launching {self._n} subagents for {self._dimension}")
        results: list[SubagentResult] = []
        finished: dict[str, bool] = {f"agent-{i}": False for i in range(self._n)}

        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop, args=(stop, finished), daemon=True,
        )
        heartbeat.start()

        try:
            with ThreadPoolExecutor(max_workers=self._n) as pool:
                futures = {pool.submit(self._run_single, i): i for i in range(self._n)}
                for future in as_completed(futures):
                    result = future.result()
                    finished[result.agent_id] = True
                    if result.success:
                        log_success(f"  {result.agent_id} finished")
                    results.append(result)
        finally:
            stop.set()
            heartbeat.join(timeout=2)

        succeeded = sum(1 for r in results if r.success)
        log_info(f"Subagent pool done: {succeeded}/{self._n} succeeded")
        return results

    @staticmethod
    def merge_jsonl(results: list[SubagentResult], output: Path) -> Path:
        """Merge JSONL files from all agents, deduplicating by (p, file, line, t).

        Returns the output path.
        """
        seen: set[tuple] = set()
        count = 0
        with open(output, "w") as out:
            for result in results:
                if not result.jsonl_file.exists():
                    continue
                with open(result.jsonl_file) as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            obj = json.loads(stripped)
                        except json.JSONDecodeError:
                            continue
                        key = (obj.get("p"), obj.get("file"), obj.get("line"), obj.get("t"))
                        if key in seen:
                            continue
                        seen.add(key)
                        out.write(stripped + "\n")
                        count += 1
        log_info(f"Merged {count} unique findings into {output.name}")
        return output
