"""Both dimension loops stop processing once run-wide cancellation is set.

After the failure-streak breaker trips (now salvaging the in-flight dimension
rather than raising), the run-wide cancellation flag is set. The loop must not
spin up the remaining dimensions only to have them short-circuit.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._loops import run_incremental_loop, run_per_dimension_loop
from quodeq.core.evidence.model import Evidence
from quodeq.shared import cancellation


@pytest.fixture(autouse=True)
def _reset_cancel():
    cancellation.reset()
    yield
    cancellation.reset()


def _mk_config(tmp_path):
    config = MagicMock()
    config.run_dir = tmp_path
    config.work_dir = tmp_path
    config.src = tmp_path
    config.source_file_count = 1
    config.options.deadline_at = None
    config.options.incremental_file_filter = None
    config.options.skip_scoring = True
    return config


def _mk_ctx():
    ctx = MagicMock()
    ctx.total = 3
    return ctx


def _ev() -> Evidence:
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=1, files_read=1, coverage_pct=100.0,
        principles={}, exit_reason="failure_streak",
    )


def _trip_on_first(calls):
    def fake_run(cfg, dim, idx, ctx, emit_log=False):
        calls.append(dim)
        cancellation.request_cancel()  # simulate a breaker trip during the first dim
        return _ev()
    return fake_run


@patch("quodeq.analysis._loops.emit_marker", lambda *a, **k: None)
def test_incremental_loop_breaks_after_cancellation(tmp_path):
    calls: list[str] = []
    runner = MagicMock()
    runner.run.side_effect = _trip_on_first(calls)
    run_incremental_loop(
        _mk_config(tmp_path), ["security", "flexibility", "usability"],
        _mk_ctx(), runner=runner,
    )
    assert calls == ["security"], "loop must stop after run-wide cancellation"


def test_per_dimension_loop_breaks_after_cancellation(tmp_path):
    calls: list[str] = []
    runner = MagicMock()
    runner.run.side_effect = _trip_on_first(calls)
    run_per_dimension_loop(
        _mk_config(tmp_path), ["security", "flexibility", "usability"],
        _mk_ctx(), runner=runner,
    )
    assert calls == ["security"], "loop must stop after run-wide cancellation"
