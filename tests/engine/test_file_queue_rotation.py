"""Tests for file queue context rotation (max_files_per_agent)."""
from pathlib import Path

import pytest

from quodeq.analysis.subagents.file_queue import FileQueue


class TestMaxFilesPerAgent:
    def test_agent_limited_to_max_files(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        files = [f"file{i}.py" for i in range(20)]
        FileQueue(queue_path, files, max_files_per_agent=10)

        q = FileQueue(queue_path)
        batch1 = q.take(5, agent_id="agent-0")
        assert len(batch1) == 5

        batch2 = q.take(5, agent_id="agent-0")
        assert len(batch2) == 5

        # Agent-0 has taken 10 files — should get nothing more
        batch3 = q.take(5, agent_id="agent-0")
        assert batch3 == []

    def test_different_agents_get_separate_budgets(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        files = [f"file{i}.py" for i in range(20)]
        FileQueue(queue_path, files, max_files_per_agent=5)

        q = FileQueue(queue_path)
        batch_a = q.take(5, agent_id="agent-0")
        assert len(batch_a) == 5

        # Agent-0 is exhausted
        assert q.take(5, agent_id="agent-0") == []

        # Agent-1 still has budget
        batch_b = q.take(5, agent_id="agent-1")
        assert len(batch_b) == 5

    def test_no_limit_when_zero(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        files = [f"file{i}.py" for i in range(10)]
        FileQueue(queue_path, files, max_files_per_agent=0)

        q = FileQueue(queue_path)
        batch = q.take(10, agent_id="agent-0")
        assert len(batch) == 10

    def test_agent_totals_persisted(self, tmp_path):
        """agent_totals dict is persisted in queue JSON for cross-process reads."""
        queue_path = tmp_path / "queue.json"
        files = [f"file{i}.py" for i in range(10)]
        FileQueue(queue_path, files, max_files_per_agent=5)

        q = FileQueue(queue_path)
        q.take(3, agent_id="agent-0")

        # Read from a fresh FileQueue instance (simulates MCP server process)
        q2 = FileQueue(queue_path)
        batch = q2.take(5, agent_id="agent-0")
        # Should only get 2 more (3 already taken)
        assert len(batch) == 2

    def test_partial_last_batch(self, tmp_path):
        queue_path = tmp_path / "queue.json"
        files = [f"file{i}.py" for i in range(10)]
        FileQueue(queue_path, files, max_files_per_agent=7)

        q = FileQueue(queue_path)
        batch1 = q.take(5, agent_id="agent-0")
        assert len(batch1) == 5

        # Only 2 left in budget even though requesting 5
        batch2 = q.take(5, agent_id="agent-0")
        assert len(batch2) == 2
