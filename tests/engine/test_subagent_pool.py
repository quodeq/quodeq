"""Tests for SubagentPool — parallel agent orchestration and JSONL merging."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool


from tests.engine.conftest import _fake_run_analysis  # noqa: F401 — shared helper


def _failing_run_analysis(work_dir, prompt, stream_file, config):
    """Mock run_analysis that raises AnalysisError."""
    stream_file.parent.mkdir(parents=True, exist_ok=True)
    stream_file.write_text("")
    if config.queue_path:
        queue = FileQueue(config.queue_path)
        queue.take(queue.remaining(), agent_id=config.agent_id)
    if config.jsonl_file:
        config.jsonl_file.write_text("")
    raise AnalysisError("CLI crashed")


class TestSubagentPool:
    def test_launches_n_agents(self, tmp_path: Path) -> None:
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=3, prompt="analyse files", dimension="maintainability"),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis", _fake_run_analysis):
            results = pool.run()

        assert len(results) >= 2  # scout + at least 1 overflow
        assert all(r.success for r in results)

    def test_agent_configs_have_queue_and_agent_id(self, tmp_path: Path) -> None:
        # NOTE: Directly tests private method _build_agent_config for coverage of
        # per-agent configuration wiring.  Known coupling to internal implementation.
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=2, prompt="test", dimension="security"),
            config=AnalysisConfig(compiled_dir=tmp_path / "compiled"),
        )

        ac, jsonl, stream = pool._build_agent_config(0)
        assert ac.queue_path == queue_path
        assert ac.agent_id == "agent-0"
        assert ac.dimension == "security"
        assert ac.compiled_dir == tmp_path / "compiled"
        assert "evidence.jsonl" in str(jsonl)  # shared JSONL
        assert "agent-0" in str(stream)

    def test_failed_agent_does_not_stop_others(self, tmp_path: Path) -> None:
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, [f"src/f{i}.py" for i in range(200)], max_files_per_agent=30)

        def _mixed_run(work_dir, prompt, stream_file, config):
            if config.agent_id == "agent-0":
                _failing_run_analysis(work_dir, prompt, stream_file, config)
            else:
                _fake_run_analysis(work_dir, prompt, stream_file, config)

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=3, prompt="test", dimension="maint"),
            config=AnalysisConfig(max_files_per_agent=30),
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis", _mixed_run):
            results = pool.run()

        failed = [r for r in results if not r.success]
        succeeded = [r for r in results if r.success]
        assert len(failed) >= 1
        assert failed[0].agent_id == "agent-0"
        assert "crashed" in failed[0].error.lower()
        assert len(succeeded) >= 1

    def test_n_agents_minimum_is_one(self, tmp_path: Path) -> None:
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])

        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=0, prompt="test", dimension="maint"),
        )

        with patch("quodeq.analysis.subagents.pool.run_analysis", _fake_run_analysis):
            results = pool.run()

        assert len(results) == 1


