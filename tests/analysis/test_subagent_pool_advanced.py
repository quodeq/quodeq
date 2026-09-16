"""Tests for SubagentPool — scout-then-scale and pool budget."""
from __future__ import annotations

import sys
import time
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.analysis.subagents._pool_models import ScaleUpState
from quodeq.analysis.subagents._pool_scaling import (
    ScaleUpContext,
    compute_scale_up,
    maybe_scale_up,
)


from tests._analysis_helpers import _fake_run_analysis  # noqa: F401 — shared helper

# See test_adaptive_scaling_integration.py for the Windows skip rationale.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)

_TEST_DIMENSION = "security"


class TestComputeScaleUp:
    """Once the scout gate opens, every free slot launches; only the queue
    size bounds the burst, never a files-per-agent estimate."""

    def test_no_remaining_returns_zero(self):
        assert compute_scale_up(0, 5) == 0

    def test_small_queue_still_fills_every_slot(self):
        # 25 files used to fit "one batch" and spawn nothing; now all 4
        # free slots launch and share the queue.
        assert compute_scale_up(25, 5) == 4

    def test_burst_never_exceeds_remaining_files(self):
        assert compute_scale_up(2, 5) == 2

    def test_burst_capped_by_max_agents(self):
        assert compute_scale_up(200, 3) == 2

    def test_max_agents_1_never_scales(self):
        assert compute_scale_up(500, 1) == 0


class _FixedQueue:
    """WorkQueue stand-in that reports a fixed remaining count."""

    def __init__(self, remaining: int) -> None:
        self._remaining = remaining

    def remaining(self) -> int:
        return self._remaining


class TestMaybeScaleUp:
    """The scout gate: nothing launches until the scout finishes or times
    out; then the burst fills every free slot the queue can feed."""

    def _ctx(self, tmp_path, remaining: int, submits: list[int]) -> ScaleUpContext:
        return ScaleUpContext(
            queue=_FixedQueue(remaining), queue_path=tmp_path / "queue.json",
            submit_fn=lambda: submits.append(1),
        )

    def test_scout_still_running_launches_nothing(self, tmp_path):
        submits: list[int] = []
        state = ScaleUpState(pool_start=time.monotonic(), max_duration=0, scout_timeout=30)

        scout_done = maybe_scale_up(set(), state, 5, self._ctx(tmp_path, 15, submits))

        assert scout_done is False
        assert submits == []

    def test_scout_done_bursts_every_free_slot(self, tmp_path):
        submits: list[int] = []
        state = ScaleUpState(pool_start=time.monotonic(), max_duration=0, scout_timeout=30)

        scout_done = maybe_scale_up({object()}, state, 5, self._ctx(tmp_path, 15, submits))

        assert scout_done is True
        assert len(submits) == 4

    def test_scout_timeout_bursts_without_waiting_for_scout(self, tmp_path):
        submits: list[int] = []
        state = ScaleUpState(pool_start=time.monotonic() - 31, max_duration=0, scout_timeout=30)

        scout_done = maybe_scale_up(set(), state, 3, self._ctx(tmp_path, 100, submits))

        assert scout_done is True
        assert len(submits) == 2


def _recording_fake(seen: list[AnalysisConfig]):
    """Wrap the suite-wide boundary fake so tests can observe the
    AnalysisConfig each worker receives through the public run() path."""
    def recording_run(work_dir, prompt, stream_file, config):
        seen.append(config)
        _fake_run_analysis(work_dir, prompt, stream_file, config)
    return recording_run


class TestMultiDimensionPool:
    def _run_pool(self, tmp_path, dimension):
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=1, prompt="test", dimension=dimension),
        )
        seen: list[AnalysisConfig] = []
        with patch(
            "quodeq.analysis.subagents._pool_worker.run_analysis",
            _recording_fake(seen),
        ):
            results = pool.run()
        assert all(r.success for r in results)
        return seen

    def test_single_dimension_backward_compat(self, tmp_path):
        """Single dimension string still works as before."""
        seen = self._run_pool(tmp_path, _TEST_DIMENSION)
        assert seen[0].dimension == _TEST_DIMENSION
        assert (tmp_path / f"{_TEST_DIMENSION}_evidence.jsonl").exists()

    def test_multi_dimension_list(self, tmp_path):
        """List of dimensions is joined into the worker config's dimension."""
        seen = self._run_pool(tmp_path, [_TEST_DIMENSION, "maintainability"])
        assert seen[0].dimension == f"{_TEST_DIMENSION},maintainability"

    def test_multi_dimension_jsonl_path(self, tmp_path):
        """Multi-dimension runs write the shared 'consolidated' JSONL."""
        self._run_pool(tmp_path, [_TEST_DIMENSION, "maintainability"])
        assert (tmp_path / "consolidated_evidence.jsonl").exists()


class TestScoutThenScale:
    def test_scout_draining_queue_launches_no_overflow(self, tmp_path):
        """No per-agent cap on the queue: the scout takes all 20 files, so
        the burst has nothing to feed and only agent-0 runs."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(20)])

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=5, prompt="analyse", dimension=_TEST_DIMENSION),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _fake_run_analysis):
            results = pool.run()

        assert len(results) == 1
        assert results[0].agent_id == "agent-0"

    def test_large_queue_scales_up(self, tmp_path):
        """200 files with max_agents=5 -> scout + overflow agents."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=5, prompt="analyse", dimension=_TEST_DIMENSION),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _fake_run_analysis):
            results = pool.run()

        assert len(results) > 1
        assert results[0].agent_id == "agent-0"

    def test_scout_first_false_launches_all_agents(self, tmp_path):
        """When scout_first=False, all agents launch immediately."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=3, prompt="verify", dimension=_TEST_DIMENSION, scout_first=False),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _fake_run_analysis):
            results = pool.run()

        # All 3 agents should have run (not just scout + scale-up)
        agent_ids = {r.agent_id for r in results}
        assert len(agent_ids) >= 3


# Time-limit behavior (the pool budget uses time_limit, not max_duration)
# is pinned publicly by tests/analysis/test_pool_exit_reason.py.
