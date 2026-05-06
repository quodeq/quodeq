"""Integration test: adaptive scaling reduces agent count for small projects."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool

# TODO(quodeq#404): SubagentPool.run() hangs on Windows inside the FileQueue
# lock acquired via msvcrt.locking. Different byte-range / past-EOF semantics
# from fcntl.flock cause the worker thread to block indefinitely under
# ThreadPoolExecutor. Pool-using tests are skipped on win32 until the
# Windows lock path is rewritten (likely with LockFileEx or by ensuring the
# .lock file always has a non-zero size before locking).
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)

_TEST_FILE_PATTERN = "src/f{}.py"


def _counting_run_analysis(call_log):
    """Factory: returns a mock run_analysis that logs agent IDs."""
    def _inner(work_dir, prompt, stream_file, config):
        stream_file.parent.mkdir(parents=True, exist_ok=True)
        stream_file.write_text("")
        call_log.append(config.agent_id)
        if config.queue_path:
            queue = FileQueue(config.queue_path)
            queue.take(queue.remaining(), agent_id=config.agent_id)
        if config.jsonl_file:
            with open(config.jsonl_file, "a") as f:
                f.write(json.dumps({
                    "schema_version": 1, "p": "Test", "t": "compliance",
                    "d": "security", "w": "ok", "file": "a.py", "line": 1,
                }) + "\n")
    return _inner


class TestAdaptiveScalingIntegration:
    def test_20_files_uses_1_agent(self, tmp_path):
        """The exact scenario from the spec: 20 files should use 1 agent."""
        call_log = []
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [_TEST_FILE_PATTERN.format(i) for i in range(20)])

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=5, prompt="analyse", dimension="security"),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis",
                    _counting_run_analysis(call_log)):
            results = pool.run()

        assert len(call_log) == 1, f"Expected 1 agent, got {len(call_log)}: {call_log}"
        assert call_log[0] == "agent-0"

    def test_200_files_scales_up(self, tmp_path):
        """200 files should trigger scale-up beyond scout."""
        call_log = []
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [_TEST_FILE_PATTERN.format(i) for i in range(200)], max_files_per_agent=30)

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=5, prompt="analyse", dimension="security"),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis",
                    _counting_run_analysis(call_log)):
            results = pool.run()

        assert len(call_log) > 1, f"Expected multiple agents, got {len(call_log)}"
        assert call_log[0] == "agent-0"  # scout always first
