"""Tests for SubagentPool — scout-then-scale and pool budget."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool, SubagentResult


from tests.engine.conftest import _fake_run_analysis  # noqa: F401 — shared helper

# See test_adaptive_scaling_integration.py for the Windows skip rationale.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)

_TEST_DIMENSION = "security"


class TestComputeScaleUp:
    def _make_pool(self, n_agents, tmp_path, max_files=30):
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["f.py"])
        return SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=n_agents, prompt="test", dimension=_TEST_DIMENSION),
            config=AnalysisConfig(max_files_per_agent=max_files),
        )

    def test_no_remaining_returns_zero(self, tmp_path):
        pool = self._make_pool(5, tmp_path)
        assert pool._compute_scale_up(0) == 0

    def test_remaining_within_one_batch(self, tmp_path):
        pool = self._make_pool(5, tmp_path)
        assert pool._compute_scale_up(25) == 0

    def test_remaining_needs_two_agents(self, tmp_path):
        pool = self._make_pool(5, tmp_path)
        assert pool._compute_scale_up(50) == 2

    def test_remaining_capped_by_max_agents(self, tmp_path):
        pool = self._make_pool(3, tmp_path)
        assert pool._compute_scale_up(200) == 2

    def test_max_agents_1_never_scales(self, tmp_path):
        pool = self._make_pool(1, tmp_path)
        assert pool._compute_scale_up(500) == 0


class TestMultiDimensionPool:
    def test_single_dimension_backward_compat(self, tmp_path):
        """Single dimension string still works as before."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=1, prompt="test", dimension=_TEST_DIMENSION),
        )
        assert pool._dimension == _TEST_DIMENSION
        assert pool._dimension_key == _TEST_DIMENSION

    def test_multi_dimension_list(self, tmp_path):
        """List of dimensions uses 'consolidated' key for file naming."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=1, prompt="test", dimension=[_TEST_DIMENSION, "maintainability"]),
        )
        assert pool._dimension == f"{_TEST_DIMENSION},maintainability"
        assert pool._dimension_key == "consolidated"
        assert pool._dimensions == [_TEST_DIMENSION, "maintainability"]

    def test_multi_dimension_jsonl_path(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=1, prompt="test", dimension=[_TEST_DIMENSION, "maintainability"]),
        )
        assert "consolidated_evidence.jsonl" in str(pool._shared_jsonl_path())


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


class TestTimeLimit:
    def test_pool_uses_time_limit_not_max_duration(self, tmp_path):
        """Pool time limit should use time_limit, not max_duration."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"f{i}.py" for i in range(5)])

        ac = AnalysisConfig(time_limit=60, max_duration=1800, max_files_per_agent=30)
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=1, prompt="test", dimension=_TEST_DIMENSION),
            config=ac,
        )
        assert pool._base_config.time_limit == 60
        assert pool._base_config.max_duration == 1800
