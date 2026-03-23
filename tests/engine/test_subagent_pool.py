"""Tests for SubagentPool — parallel agent orchestration and JSONL merging."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError
from quodeq.engine.file_queue import FileQueue
from quodeq.engine.subagent_pool import PoolOptions, PoolPaths, SubagentPool, SubagentResult


def _fake_run_analysis(work_dir, prompt, stream_file, config):
    """Mock run_analysis that writes some findings and drains the queue."""
    stream_file.parent.mkdir(parents=True, exist_ok=True)
    stream_file.write_text("")  # empty stream
    # Drain the queue so the pool doesn't respawn agents indefinitely
    if config.queue_path:
        queue = FileQueue(config.queue_path)
        queue.take(queue.remaining(), agent_id=config.agent_id)
    if config.jsonl_file:
        agent_id = config.agent_id or "unknown"
        with open(config.jsonl_file, "a") as f:
            f.write(json.dumps({
                "schema_version": 1,
                "p": "Modularity", "t": "violation", "d": "maintainability",
                "w": f"Found by {agent_id}", "file": f"{agent_id}.py", "line": 1,
            }) + "\n")


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


class TestMergeJsonl:
    def _make_result(self, tmp_path: Path, agent_id: str, findings: list[dict]) -> SubagentResult:
        jsonl = tmp_path / f"{agent_id}.jsonl"
        with open(jsonl, "w") as f:
            for finding in findings:
                f.write(json.dumps(finding) + "\n")
        return SubagentResult(
            agent_id=agent_id, jsonl_file=jsonl,
            stream_file=tmp_path / f"{agent_id}.stream", success=True,
        )

    def test_merges_unique_findings(self, tmp_path: Path) -> None:
        r1 = self._make_result(tmp_path, "a0", [
            {"p": "P1", "t": "violation", "file": "a.py", "line": 1},
            {"p": "P2", "t": "compliance", "file": "b.py", "line": 2},
        ])
        r2 = self._make_result(tmp_path, "a1", [
            {"p": "P3", "t": "violation", "file": "c.py", "line": 3},
        ])

        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r1, r2], output)

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_deduplicates_across_agents(self, tmp_path: Path) -> None:
        finding = {"p": "P1", "t": "violation", "file": "a.py", "line": 10}
        r1 = self._make_result(tmp_path, "a0", [finding])
        r2 = self._make_result(tmp_path, "a1", [finding])

        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r1, r2], output)

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_skips_missing_jsonl(self, tmp_path: Path) -> None:
        r = SubagentResult(
            agent_id="a0",
            jsonl_file=tmp_path / "nonexistent.jsonl",
            stream_file=tmp_path / "a0.stream",
            success=False,
        )
        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r], output)
        assert output.read_text() == ""

    def test_empty_results_produce_empty_file(self, tmp_path: Path) -> None:
        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([], output)
        assert output.read_text() == ""

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "bad.jsonl"
        jsonl.write_text("not json\n" + json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1}) + "\n")
        r = SubagentResult(agent_id="a0", jsonl_file=jsonl, stream_file=tmp_path / "a0.stream", success=True)

        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r], output)

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 1


