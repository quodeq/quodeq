"""SubagentPool: one agent's future is a task-entry fault-isolation boundary.

An exception a pool worker's own narrow handling doesn't already recognise
must not crash the whole pool run; see ``run_isolated`` in _pool_scaling.py.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.shared.log_sink import SHARED_LOG

from tests._analysis_helpers import _fake_run_analysis

# See test_scout_burst_integration.py for the Windows skip rationale.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)

_TEST_DIMENSION = "security"


def _run_fn_agent0_raises_attribute_error(work_dir, prompt, stream_file, config):
    """Stand-in for a worker's own run_fn: agent-0 hits a bug, the rest are fine."""
    if config.agent_id == "agent-0":
        raise AttributeError("'NoneType' object has no attribute 'x'")
    return _fake_run_analysis(work_dir, prompt, stream_file, config)


class TestPoolSurvivesAnUnexpectedWorkerException:
    def test_unexpected_exception_marks_one_agent_failed_and_others_still_run(
        self, tmp_path, monkeypatch,
    ):
        """An AttributeError from one agent's run_fn (not one of the pool's
        already-narrowed failure types) must not crash the whole pool: the
        dead agent is marked failed and the rest of the pool keeps going,
        with a warning (and its traceback) logged for the dead one."""
        warnings: list[str] = []
        monkeypatch.setattr(SHARED_LOG, "warning", warnings.append)

        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(4)])

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=2, prompt="analyse", dimension=_TEST_DIMENSION, scout_first=False),
            config=AnalysisConfig(),
        )

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _run_fn_agent0_raises_attribute_error):
            results = pool.run()

        by_id = {r.agent_id: r for r in results}
        assert by_id["agent-0"].success is False
        assert "no attribute" in by_id["agent-0"].error
        assert any(r.success for r in results if r.agent_id != "agent-0")
        assert any("AttributeError" in w and "Traceback" in w for w in warnings)
