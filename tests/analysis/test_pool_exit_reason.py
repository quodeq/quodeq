"""Verify SubagentPool.exit_reason reflects the actual exit path."""
from __future__ import annotations

import time
from unittest.mock import patch
from pathlib import Path

from quodeq.analysis.subagents.pool import SubagentPool
from quodeq.analysis.subagents._pool_models import PoolOptions, PoolPaths
from quodeq.analysis.subprocess import AnalysisConfig


def _build_pool(tmp_path: Path, time_limit: int = 0, deadline_at: float | None = None) -> SubagentPool:
    work = tmp_path / "work"
    work.mkdir()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    queue = tmp_path / "queue.json"
    queue.write_text('{"files": []}', encoding="utf-8")
    return SubagentPool(
        paths=PoolPaths(work_dir=work, evidence_dir=evidence, queue_path=queue),
        options=PoolOptions(n_agents=1, prompt="p", dimension="security", scout_first=False),
        config=AnalysisConfig(time_limit=time_limit, deadline_at=deadline_at),
    )


def test_pool_exit_reason_defaults_to_done_on_natural_drain(tmp_path):
    pool = _build_pool(tmp_path)
    # Patch both loops to be no-ops so the with-block exits immediately.
    with patch("quodeq.analysis.subagents.pool.scout_loop"), \
         patch("quodeq.analysis.subagents.pool.immediate_loop"):
        pool.run()
    assert pool.exit_reason == "done"


def test_pool_exit_reason_time_limit_when_elapsed_exceeds_budget(tmp_path):
    pool = _build_pool(tmp_path, time_limit=1)  # 1-second budget
    # Make the loop sleep past the budget before returning.

    def _slow_loop(ctx):
        time.sleep(1.1)
    with patch("quodeq.analysis.subagents.pool.scout_loop", side_effect=_slow_loop), \
         patch("quodeq.analysis.subagents.pool.immediate_loop", side_effect=_slow_loop):
        pool.run()
    assert pool.exit_reason == "time_limit"


def test_pool_exit_reason_error_when_loop_raises(tmp_path):
    pool = _build_pool(tmp_path)

    def _raise(ctx):
        raise RuntimeError("boom")
    with patch("quodeq.analysis.subagents.pool.scout_loop", side_effect=_raise), \
         patch("quodeq.analysis.subagents.pool.immediate_loop", side_effect=_raise):
        try:
            pool.run()
        except RuntimeError:
            pass
    assert pool.exit_reason == "error"


def _queue_with_files(tmp_path: Path, n: int) -> None:
    from quodeq.analysis.subagents.file_queue import FileQueue  # noqa: PLC0415

    FileQueue(tmp_path / "queue.json", [f"f{i}.py" for i in range(n)])


def test_pool_exit_reason_time_limit_when_the_slice_ends_with_files_left(tmp_path):
    """A dimension's slice of the run deadline passing with work queued is a time limit."""
    pool = _build_pool(tmp_path, deadline_at=time.monotonic() - 1)
    _queue_with_files(tmp_path, 3)
    with patch("quodeq.analysis.subagents.pool.scout_loop"), \
         patch("quodeq.analysis.subagents.pool.immediate_loop"):
        pool.run()
    assert pool.exit_reason == "time_limit"


def test_pool_exit_reason_done_when_the_slice_ends_after_the_queue_drained(tmp_path):
    pool = _build_pool(tmp_path, deadline_at=time.monotonic() - 1)
    _queue_with_files(tmp_path, 0)
    with patch("quodeq.analysis.subagents.pool.scout_loop"), \
         patch("quodeq.analysis.subagents.pool.immediate_loop"):
        pool.run()
    assert pool.exit_reason == "done"
