"""The dimension loops report the per-run drop-ratio aggregate (issue #606).

Both loop orchestrators end with the post-run guards (zero-findings,
model-reachability). The drop-stats report must run there too — once per
run, before the guards so the summary lands even when a guard raises. The
loop is also where the ``drop_stats`` dashboard marker is emitted (the
composition root for this seam, per ``_drop_stats.report_run_drop_stats``'s
own docstring) -- exactly once when the run parsed anything, never when it
didn't.

The loops are exercised with an empty dimension list: the loop body never
runs, but the end-of-loop reporting and guards do, which is exactly the
seam under test.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.analysis import _drop_stats
from quodeq.analysis._loops import LoopDeps, run_incremental_loop, run_per_dimension_loop
from tests.conftest import RecordingLog


def _loop_config(drop_counter: _drop_stats.DropStatsCounter | None) -> MagicMock:
    # The counter now lives on the RunConfig (a field, not a LoopDeps
    # collaborator) so pool worker threads of one run share it; the
    # MagicMock stand-in carries it the same way a real RunConfig would.
    config = MagicMock()
    config.options.deadline_at = None
    config.options.incremental_file_filter = None
    config.options.skip_scoring = False
    config.drop_counter = drop_counter
    return config


def test_per_dimension_loop_reports_drop_stats_at_end():
    # An injected counter, not the module-default: isolation via injection,
    # not fixture-patched module state.
    counter = _drop_stats.DropStatsCounter()
    counter.record(dropped=1, kept=9)
    log = RecordingLog()
    run_per_dimension_loop(
        _loop_config(counter), [], MagicMock(),
        LoopDeps(runner=MagicMock(), log=log),
    )
    assert any("dropped 1 of 10" in m for m in log.info_messages)
    # The loop's report consumed the accumulator.
    assert counter.consume().parsed == 0


def test_incremental_loop_reports_drop_stats_at_end():
    counter = _drop_stats.DropStatsCounter()
    counter.record(dropped=1, kept=9)
    log = RecordingLog()
    run_incremental_loop(
        _loop_config(counter), [], MagicMock(),
        LoopDeps(runner=MagicMock(), log=log),
    )
    assert any("dropped 1 of 10" in m for m in log.info_messages)
    assert counter.consume().parsed == 0


def test_per_dimension_loop_emits_drop_stats_marker_exactly_once():
    """Structured marker for the dashboard / SSE stream, mirroring the
    per-dim ``cache_stats`` marker pattern -- emitted by the loop, the
    composition root for this seam, not by ``report_run_drop_stats``."""
    counter = _drop_stats.DropStatsCounter()
    counter.record(dropped=2, kept=8)

    with patch("quodeq.analysis._loops.emit_marker") as mock_emit:
        run_per_dimension_loop(
            _loop_config(counter), [], MagicMock(),
            LoopDeps(runner=MagicMock()),
        )

    drop_calls = [c for c in mock_emit.call_args_list if c.args[:1] == ("drop_stats",)]
    assert len(drop_calls) == 1
    assert drop_calls[0].kwargs == {"dropped": 2, "kept": 8, "ratio": 0.2}


def test_incremental_loop_emits_no_marker_when_nothing_parsed():
    """CLI-provider runs (no API calls) must not gain a spurious marker."""
    with patch("quodeq.analysis._loops.emit_marker") as mock_emit:
        run_incremental_loop(
            _loop_config(_drop_stats.DropStatsCounter()), [], MagicMock(),
            LoopDeps(runner=MagicMock()),
        )

    drop_calls = [c for c in mock_emit.call_args_list if c.args[:1] == ("drop_stats",)]
    assert drop_calls == []
