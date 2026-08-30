"""The dimension loops report the per-run drop-ratio aggregate (issue #606).

Both loop orchestrators end with the post-run guards (zero-findings,
model-reachability). The drop-stats report must run there too — once per
run, before the guards so the summary lands even when a guard raises.

The loops are exercised with an empty dimension list: the loop body never
runs, but the end-of-loop reporting and guards do, which is exactly the
seam under test.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from quodeq.analysis import _drop_stats
from quodeq.analysis._loops import run_incremental_loop, run_per_dimension_loop


@pytest.fixture(autouse=True)
def _propagate_quodeq_logs():
    # The quodeq logger has propagate=False (StderrHandler only); flip it so
    # pytest's caplog handler (on the root logger) receives the records.
    qlog = logging.getLogger("quodeq")
    orig = qlog.propagate
    qlog.propagate = True
    yield
    qlog.propagate = orig


def _loop_config() -> MagicMock:
    config = MagicMock()
    config.options.deadline_at = None
    config.options.incremental_file_filter = None
    config.options.skip_scoring = False
    return config


def test_per_dimension_loop_reports_drop_stats_at_end(caplog):
    # An injected counter, not the module-default: isolation via injection,
    # not fixture-patched module state.
    counter = _drop_stats.DropStatsCounter()
    counter.record(dropped=1, kept=9)
    with caplog.at_level(logging.INFO):
        run_per_dimension_loop(_loop_config(), [], MagicMock(), runner=MagicMock(), drop_counter=counter)
    assert "dropped 1 of 10" in caplog.text
    # The loop's report consumed the accumulator.
    assert counter.consume().parsed == 0


def test_incremental_loop_reports_drop_stats_at_end(caplog):
    counter = _drop_stats.DropStatsCounter()
    counter.record(dropped=1, kept=9)
    with caplog.at_level(logging.INFO):
        run_incremental_loop(_loop_config(), [], MagicMock(), runner=MagicMock(), drop_counter=counter)
    assert "dropped 1 of 10" in caplog.text
    assert counter.consume().parsed == 0
