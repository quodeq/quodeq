"""Tests for run-level deadline enforcement in the dim loops."""
import time
from unittest.mock import MagicMock

from quodeq.analysis._loops import run_per_dimension_loop


def _mk_config(deadline_at):
    config = MagicMock()
    config.options.deadline_at = deadline_at
    config.options.incremental_file_filter = None
    # skip_scoring=True bypasses check_zero_findings, which would otherwise
    # walk the MagicMock Evidence and raise EvaluationError.
    config.options.skip_scoring = True
    config.source_file_count = 10
    return config


def _mk_runner(return_value=None, side_effect=None):
    """A DimensionRunner-shaped mock; tests inspect runner.run.call_count."""
    runner = MagicMock()
    if side_effect is not None:
        runner.run.side_effect = side_effect
    else:
        runner.run.return_value = return_value
    return runner


def test_loop_skips_all_dims_when_deadline_already_past():
    config = _mk_config(time.monotonic() - 1)
    ctx = MagicMock(total=3)
    runner = _mk_runner(return_value=MagicMock())

    result = run_per_dimension_loop(
        config, ["a", "b", "c"], ctx,
        runner=runner,
    )

    assert runner.run.call_count == 0
    assert result == {}


def test_loop_runs_first_dim_then_skips_remaining(monkeypatch):
    deadline = time.monotonic() + 0.1
    fake_now = [time.monotonic()]

    monkeypatch.setattr(
        "quodeq.analysis._loops.time.monotonic",
        lambda: fake_now[0],
    )

    config = _mk_config(deadline)
    ctx = MagicMock(total=3)

    ev = MagicMock()
    def fake_process(_cfg, _dim, _idx, _ctx, *, emit_log=True):
        # First dim runs, consumes the budget, then deadline passes
        fake_now[0] = deadline + 0.01
        return ev
    runner = _mk_runner(side_effect=fake_process)

    result = run_per_dimension_loop(
        config, ["a", "b", "c"], ctx,
        runner=runner,
    )

    assert runner.run.call_count == 1
    assert "a" in result
    assert "b" not in result
    assert "c" not in result


def test_loop_runs_all_dims_when_no_deadline():
    config = _mk_config(None)
    ctx = MagicMock(total=2)
    runner = _mk_runner(return_value=MagicMock())

    result = run_per_dimension_loop(
        config, ["a", "b"], ctx,
        runner=runner,
    )

    assert runner.run.call_count == 2
    assert "a" in result and "b" in result
