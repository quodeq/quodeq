"""Integration tests for file prioritization and pool budget."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.pool import PoolOptions, PoolPaths, SubagentPool


class TestPrioritizationInFileQueue:
    def test_security_prioritizes_auth_over_tests(self, tmp_path):
        """Auth files should be queued before test files for security analysis."""
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "auth.py").write_text("def login(): pass")
        (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
        (tmp_path / "tests" / "test_utils.py").write_text("def test(): pass")

        from quodeq.analysis.subagents.priority import prioritize_files
        files = ["tests/test_utils.py", "src/utils.py", "src/auth.py"]
        result = prioritize_files(files, tmp_path, "security")

        # Auth file should come first (security keyword + src/ path)
        assert result[0] == "src/auth.py"
        # Test file should come last (low base score, no security keyword)
        assert result[-1] == "tests/test_utils.py"

        # Feed to FileQueue and verify order preserved
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, result, max_files_per_agent=50)
        queue = FileQueue(queue_path)
        taken = queue.take(3)
        assert taken[0] == "src/auth.py"


class TestPoolBudgetFlow:
    def test_pool_budget_from_analysis_options(self, tmp_path):
        """Verify pool_budget on AnalysisConfig is used by SubagentPool."""
        queue_path = tmp_path / "queue.json"
        FileQueue(queue_path, ["f.py"])

        ac = AnalysisConfig(pool_budget=120, max_duration=1800, max_files_per_agent=50)
        pool = SubagentPool(
            paths=PoolPaths(work_dir=tmp_path, evidence_dir=tmp_path, queue_path=queue_path),
            options=PoolOptions(n_agents=1, prompt="test", dimension="security"),
            config=ac,
        )

        # Pool budget should be 120 (custom), not 600 (default)
        assert pool._base_config.pool_budget == 120
        # Per-agent duration should still be 1800, not affected by pool_budget
        assert pool._base_config.max_duration == 1800
