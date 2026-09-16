"""Integration tests: scout-then-scale pool sizing through SubagentPool.run().

The fakes here take a fixed number of files per agent and hold the slot for
a moment, so the pool's launch decisions are observable: how many agents ran
in total, and how many ran at the same time.
"""
from __future__ import annotations

import sys
import threading
import time
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
# Long enough for every agent launched in one loop iteration to be running
# at once before any of them touches the queue; short enough to keep the
# tests quick.
_HOLD_S = 0.5


class _Batching:
    """run_analysis fake: each agent holds its slot, then takes *take* files."""

    def __init__(self, take: int) -> None:
        self.take = take
        self.agent_ids: list[str] = []
        self.max_concurrent = 0
        self._running = 0
        self._lock = threading.Lock()

    def __call__(self, work_dir, prompt, stream_file, config) -> None:
        stream_file.parent.mkdir(parents=True, exist_ok=True)
        stream_file.write_text("")
        with self._lock:
            self.agent_ids.append(config.agent_id)
            self._running += 1
            self.max_concurrent = max(self.max_concurrent, self._running)
        time.sleep(_HOLD_S)
        FileQueue(config.queue_path).take(self.take, agent_id=config.agent_id)
        with self._lock:
            self._running -= 1


def _run_pool(tmp_path, n_files: int, n_agents: int, fake: _Batching) -> None:
    queue_path = tmp_path / "queue.json"
    FileQueue(queue_path, [_TEST_FILE_PATTERN.format(i) for i in range(n_files)])
    pool = SubagentPool(
        paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
        options=PoolOptions(n_agents=n_agents, prompt="analyse", dimension="security"),
        config=AnalysisConfig(),
    )
    with patch("quodeq.analysis.subagents._pool_worker.run_analysis", fake):
        pool.run()


class TestScoutThenScaleIntegration:
    def test_small_queue_runs_the_whole_pool_at_once(self, tmp_path):
        """20 files, 3 per take, 5 agents: the old estimate kept this on one
        agent; now the scout's completion fills all five slots together."""
        fake = _Batching(take=3)

        _run_pool(tmp_path, n_files=20, n_agents=5, fake=fake)

        assert fake.agent_ids[0] == "agent-0"  # scout always first
        assert fake.max_concurrent == 5

    def test_never_launches_more_agents_than_files_left(self, tmp_path):
        """4 files, 1 per take, 5 agents: after the scout took one, exactly
        three more launch. The scout's own slot is not respawned on top."""
        fake = _Batching(take=1)

        _run_pool(tmp_path, n_files=4, n_agents=5, fake=fake)

        assert len(fake.agent_ids) == 4, fake.agent_ids
