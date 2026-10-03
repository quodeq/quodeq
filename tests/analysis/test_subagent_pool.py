"""Tests for SubagentPool — parallel agent orchestration and JSONL merging."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.run_types import RunConfig
from quodeq.analysis.subprocess import AnalysisConfig, AnalysisError
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool
from quodeq.analysis.subagents._pool_worker import WorkerContext, build_agent_config


from tests._analysis_helpers import _fake_run_analysis  # shared helper

# See test_scout_burst_integration.py for the Windows skip rationale.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)


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

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _fake_run_analysis):
            results = pool.run()

        assert len(results) >= 2  # scout + at least 1 overflow
        assert all(r.success for r in results)

    def test_agent_configs_have_queue_and_agent_id(self, tmp_path: Path) -> None:
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["a.py"])

        wctx = WorkerContext(
            dimension="security", dimension_key="security",
            evidence_dir=tmp_path, queue_path=queue_path,
        )
        ac, jsonl, stream = build_agent_config(
            0, AnalysisConfig(compiled_dir=tmp_path / "compiled"), wctx,
        )
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

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _mixed_run):
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

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _fake_run_analysis):
            results = pool.run()

        assert len(results) == 1


class TestSuppressionPredicateEvaluatorsDir:
    """The pool's suppression matcher reads its evaluators dir off
    base_config.run_config (row 9184), the same value _start_heartbeat's
    principle resolver already reads -- not the process-global default."""

    def _pool(self, tmp_path: Path, evaluators_dir: Path | None) -> SubagentPool:
        project_dir = tmp_path / "project"
        run_dir = project_dir / "run1"
        (run_dir / "evidence").mkdir(parents=True)
        (project_dir / "deleted.json").write_text(json.dumps(
            [{"dimension": "reliability", "principle": "Fault Tolerance", "file": "a.py"}]))
        run_config = RunConfig(src=tmp_path, language="python", evaluators_dir=evaluators_dir)
        return SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=run_dir / "evidence",
                            queue_path=tmp_path / "queue.json"),
            options=PoolOptions(n_agents=1, prompt="p", dimension="reliability"),
            config=AnalysisConfig(run_config=run_config),
        )

    def test_matcher_uses_run_configs_evaluators_dir(self, tmp_path: Path) -> None:
        evaluators_dir = tmp_path / "run-evaluators"
        evaluators_dir.mkdir()
        (evaluators_dir / "reliability.json").write_text(json.dumps(
            {"principles": [{"name": "Fault Tolerance", "requirements": [{"id": "R-FT-1"}]}]}))
        pool = self._pool(tmp_path, evaluators_dir)

        suppressed = pool._suppression_predicate()

        assert suppressed is not None
        assert suppressed({"t": "violation", "p": "R-FT-1", "file": "a.py", "line": 1})

    def test_no_run_config_evaluators_dir_falls_back_to_the_global_default_only(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """With no run_config.evaluators_dir, the matcher falls back to the
        process-global default (build_matcher's own call-time default), not
        some other value: pins that the pool reads run_config first and only
        reaches the global default when run_config carries none."""
        global_dir = tmp_path / "global-evaluators"  # deliberately has no mapping
        global_dir.mkdir()
        import quodeq.services.suppression as suppression_mod
        monkeypatch.setattr(suppression_mod, "default_paths", lambda: type(
            "P", (), {"evaluators_dir": global_dir})())
        pool = self._pool(tmp_path, None)

        suppressed = pool._suppression_predicate()

        assert suppressed is not None
        assert not suppressed({"t": "violation", "p": "R-FT-1", "file": "a.py", "line": 1})


