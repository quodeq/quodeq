"""Tests for SubagentPool — scout-then-scale and pool budget."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.analysis.subagents._pool_scaling import compute_scale_up


from tests._analysis_helpers import _fake_run_analysis  # noqa: F401 — shared helper

# See test_adaptive_scaling_integration.py for the Windows skip rationale.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)

_TEST_DIMENSION = "security"


class TestComputeScaleUp:
    def test_no_remaining_returns_zero(self):
        assert compute_scale_up(0, 5, 30) == 0

    def test_remaining_within_one_batch(self):
        assert compute_scale_up(25, 5, 30) == 0

    def test_remaining_needs_two_agents(self):
        assert compute_scale_up(50, 5, 30) == 2

    def test_remaining_capped_by_max_agents(self):
        assert compute_scale_up(200, 3, 30) == 2

    def test_max_agents_1_never_scales(self):
        assert compute_scale_up(500, 1, 30) == 0


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
    def test_small_queue_uses_one_agent(self, tmp_path):
        """20 files with max_agents=5 -> only 1 agent should run (scout handles all)."""
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
