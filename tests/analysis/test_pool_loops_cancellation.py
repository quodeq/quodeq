"""Pool loops take their cancellation check from LoopContext, not the global.

``scout_loop``/``immediate_loop`` used to read the process-wide
``quodeq.shared.cancellation`` singleton directly; the check is now a
``LoopContext`` field whose default binds the singleton at the composition
seam, so a test can cancel a loop without mutating process-wide state.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.analysis.subagents._pool_loops import (
    LoopContext,
    immediate_loop,
    scout_loop,
)
from quodeq.shared import cancellation


def _ctx(tmp_path: Path, **overrides) -> LoopContext:
    kwargs = dict(
        futures={}, finished={}, results=[],
        max_duration=0.0, pool_start=0.0, n_agents=2,
        queue=None, queue_path=tmp_path / "queue.json",
        shared_jsonl_path=tmp_path / "shared.jsonl",
        evidence_dir=tmp_path, dimension_key="security",
        submit_fn=MagicMock(),
    )
    kwargs.update(overrides)
    return LoopContext(**kwargs)


@pytest.mark.parametrize("loop", [scout_loop, immediate_loop])
def test_loop_exits_on_injected_cancellation_without_touching_global(loop, tmp_path):
    ctx = _ctx(tmp_path, is_cancelled=lambda: True)
    loop(ctx)
    ctx.submit_fn.assert_not_called()
    assert not cancellation.is_cancelled()  # the process global stayed untouched


@pytest.mark.parametrize("loop", [scout_loop, immediate_loop])
def test_loop_proceeds_when_injected_check_is_false(loop, tmp_path):
    ctx = _ctx(tmp_path, is_cancelled=lambda: False)
    loop(ctx)  # futures stay empty, so the loop drains immediately
    assert ctx.submit_fn.call_count >= 1


def test_default_wiring_honors_the_process_global(tmp_path):
    # Production constructs LoopContext without is_cancelled; the default must
    # still observe request_cancel() on the shared singleton.
    ctx = _ctx(tmp_path)
    assert ctx.is_cancelled is cancellation.is_cancelled
    cancellation.request_cancel()
    try:
        scout_loop(ctx)
        immediate_loop(ctx)
    finally:
        cancellation.reset()
    ctx.submit_fn.assert_not_called()
