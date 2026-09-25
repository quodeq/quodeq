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
    AGENT_ID_PREFIX,
    HEARTBEAT_JOIN_TIMEOUT_S,
)
from quodeq.analysis.subagents._pool_worker import WorkerContext, build_agent_config, run_single_agent
from quodeq.analysis.subagents.file_queue import WorkQueue
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl, merge_jsonl
from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.core.evidence.req_mapping import build_principle_resolver
from quodeq.core.run.exit_reason import ExitReason
from quodeq.data.fs.standards_loader import read_req_to_principle_map
from quodeq.shared.constants import CONSOLIDATED_DIMENSION_KEY, DEFAULT_TIME_LIMIT
from quodeq.shared.logging import log_info, log_warning

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
            self._dimension_key = CONSOLIDATED_DIMENSION_KEY
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
        self._agent_failure_streak_limit = options.agent_failure_streak_limit
        self._futures: dict[Future[SubagentResult], int] = {}
        self._finished: dict[str, bool] = {}
        self._next_idx = 0
        self.exit_reason: str = ExitReason.DONE

    def _shared_jsonl_path(self) -> Path:
        return self._evidence_dir / f"{self._dimension_key}_evidence.jsonl"

    def _build_agent_config(self, idx: int) -> tuple[AnalysisConfig, Path, Path]:
        return build_agent_config(idx, self._base_config, self._worker_ctx)

    def _run_single(self, idx: int) -> SubagentResult:
        return run_single_agent(
            idx, self._work_dir, self._prompt, self._base_config,
            self._worker_ctx,
        )

    def _submit_agent(self, executor: ThreadPoolExecutor) -> None:
        self._finished[f"{AGENT_ID_PREFIX}-{self._next_idx}"] = False
        self._futures[executor.submit(self._run_single, self._next_idx)] = self._next_idx
        self._next_idx += 1

    def _run_config_evaluators_dir(self) -> Path | None:
        """The run's evaluators dir, read off ``base_config.run_config`` the
        same way the heartbeat's principle resolver reads it -- so the
        suppression matcher and the resolver never disagree on which
        custom-evaluator files exist. None (not the global default) when the
        run has no evaluators dir configured."""
        run_config = getattr(self._base_config, "run_config", None)
        return getattr(run_config, "evaluators_dir", None)

    def _suppression_predicate(self):
        """Predicate the heartbeat uses to net dismissed/deleted findings out.

        Built once per pool, not per tick: the stores are read here and the
        resulting matcher is immutable, so a heartbeat firing every 10s costs
        no extra file reads. Suppression state is project-scoped and the
        evidence dir is ``<project>/<run>/evidence``.

        Returns None when the project has no suppressions, when the layout
        isn't the expected one, or for consolidated runs — whose synthetic
        dimension key would never match a real delete key anyway. The counts
        then stay raw, which is the pre-existing behaviour.
        """
        if self._dimension_key == CONSOLIDATED_DIMENSION_KEY:
            return None
        try:
            from quodeq.services.suppression import matcher_for  # noqa: PLC0415
            project_dir = self._evidence_dir.parent.parent
            matcher = matcher_for(
                project_dir, self._dimension_key,
                evaluators_dir=self._run_config_evaluators_dir(),
            )
        except (ImportError, OSError, ValueError) as exc:
            log_warning(f"Suppression state unavailable, counts stay raw: {exc}")
            return None
        return matcher.is_suppressed if matcher.active else None

    def _start_heartbeat(self) -> tuple[threading.Event, threading.Thread]:
        stop = threading.Event()
        ctx = HeartbeatContext(
            queue_path=self._queue_path, dimension_key=self._dimension_key,
            jsonl_path=self._shared_jsonl_path(), lock=self._jsonl_lock,
            suppressed=self._suppression_predicate(),
            # Same standard the evidence parser uses at end of run, so the
            # heartbeat counts what the report will keep.
            resolver=build_principle_resolver(
                self._dimension_key,
                self._run_config_evaluators_dir(),
                self._base_config.compiled_dir,
                req_map_reader=read_req_to_principle_map,
            ),
        )
        hb = threading.Thread(
            target=heartbeat_loop, args=(stop, self._finished, ctx), daemon=True,
        )
        hb.start()
        return stop, hb

    def _log_launch(self) -> None:
        if self._scout_first:
            log_info(f"[{self._phase}] Launching scout agent for {self._dimension_key} (max {self._n} agents)")
        else:
            log_info(f"[{self._phase}] Launching {self._n} agents for {self._dimension_key}")

    def _reset_run_state(self) -> None:
        self._finished.clear()
        self._futures.clear()
        self._next_idx = 0

    def _run_loops(self, results: list[SubagentResult], max_dur: int, pool_start: float) -> None:
        """Drive the scout or immediate dispatch loop on a fresh executor."""
        with ThreadPoolExecutor(max_workers=self._n) as pool:
            ctx = LoopContext(
                futures=self._futures, finished=self._finished, results=results,
                max_duration=max_dur, pool_start=pool_start,
                n_agents=self._n,
                queue=self._queue, queue_path=self._queue_path,
                shared_jsonl_path=self._shared_jsonl_path(),
                evidence_dir=self._evidence_dir, dimension_key=self._dimension_key,
                submit_fn=lambda: self._submit_agent(pool),
                deadline_at=self._base_config.deadline_at,
                run_deadline_at=self._base_config.run_deadline_at,
                agent_failure_streak_limit=self._agent_failure_streak_limit,
            )
            if self._scout_first:
                scout_loop(ctx)
            else:
                immediate_loop(ctx)

    def _run_with_heartbeat(self, results: list[SubagentResult], max_dur: int, pool_start: float) -> None:
        """Run the loops with the heartbeat thread alive; mark errors on the way out."""
        stop, hb = self._start_heartbeat()
        try:
            self._run_loops(results, max_dur, pool_start)
        except BaseException:
            self.exit_reason = ExitReason.ERROR
            raise
        finally:
            stop.set()
            hb.join(timeout=HEARTBEAT_JOIN_TIMEOUT_S)

    def _record_exit_reason(self, max_dur: int, pool_start: float) -> None:
        """Without an exception, decide between "done" and "time_limit"."""
        elapsed = time.monotonic() - pool_start
        if max_dur > 0 and elapsed >= max_dur:
            self.exit_reason = ExitReason.TIME_LIMIT

    def run(self) -> list[SubagentResult]:
        """Launch agents in parallel, returning a SubagentResult per agent."""
        self.exit_reason = ExitReason.DONE
        max_dur = self._base_config.time_limit if self._base_config.time_limit is not None else DEFAULT_TIME_LIMIT
        pool_start = time.monotonic()
        self._log_launch()
        results: list[SubagentResult] = []
        self._reset_run_state()
        self._run_with_heartbeat(results, max_dur, pool_start)
        self._record_exit_reason(max_dur, pool_start)
        succeeded = sum(1 for r in results if r.success)
        log_info(f"Subagent pool done: {succeeded}/{self._next_idx} agents ran, {succeeded} succeeded")
        return results

    @staticmethod
    def deduplicate_jsonl(jsonl_path: Path) -> int:
        """Rewrite *jsonl_path* without duplicate findings. Returns the number
        of lines dropped."""
        return deduplicate_jsonl(jsonl_path)

    @staticmethod
    def merge_jsonl(results: list[SubagentResult], output: Path) -> Path:
        """Concatenate every agent's JSONL into *output*, deduplicating as it
        goes. Returns *output*."""
        return merge_jsonl((r.jsonl_file for r in results), output)
