"""Tests for the run-deadline gate in should_respawn.

Without the gate, a pool whose per-agent budget has been clamped to
``max(1, deadline_at - now)`` would die in ~1s, get respawned, die again,
and so on — pumping out 1-second agents indefinitely until the pool's
local *max_duration* finally fired. The gate makes ``should_respawn``
return 0 once the run-level deadline has passed, mirroring the existing
behaviour for the pool-local time limit.
"""
import time
from pathlib import Path

from quodeq.analysis.subagents._pool_scaling import should_respawn
from quodeq.analysis.subagents.file_queue import FileQueue


def _queue(tmp_path: Path, files: int = 5) -> FileQueue:
    return FileQueue(tmp_path / "queue.json", files=[f"f{i}.py" for i in range(files)])


def test_respawn_blocked_when_run_deadline_passed(tmp_path):
    queue = _queue(tmp_path, files=5)
    # Pool itself still has budget left, but the run deadline is in the past.
    assert should_respawn(
        queue, queue._path,
        pool_start=time.monotonic(),
        max_duration=600,
        deadline_at=time.monotonic() - 1,
    ) == 0


def test_respawn_allowed_before_run_deadline(tmp_path):
    queue = _queue(tmp_path, files=5)
    assert should_respawn(
        queue, queue._path,
        pool_start=time.monotonic(),
        max_duration=600,
        deadline_at=time.monotonic() + 60,
    ) == 5


def test_respawn_pool_limit_still_enforced_without_deadline(tmp_path):
    queue = _queue(tmp_path, files=5)
    # No run deadline — pool-local budget alone must still gate respawn.
    assert should_respawn(
        queue, queue._path,
        pool_start=time.monotonic() - 700,
        max_duration=600,
        deadline_at=None,
    ) == 0


def test_respawn_unlimited_when_no_constraints(tmp_path):
    queue = _queue(tmp_path, files=5)
    assert should_respawn(
        queue, queue._path,
        pool_start=time.monotonic(),
        max_duration=0,        # 0 = unlimited pool budget
        deadline_at=None,
    ) == 5
