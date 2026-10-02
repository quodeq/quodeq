"""The failure-streak breaker ends a dimension, not necessarily the run.

Whether the run-wide cancel survives the trip depends on what the
dimension analysed before the streak. The dispatchers come from the
breaker salvage tests, which model the same two shapes.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
from quodeq.analysis.cache.failure_streak import CircuitBreakerError
from quodeq.analysis.errors import REASON_CIRCUIT_BREAKER
from tests.analysis.cache.conftest import _make_callbacks, _make_ctx, _setup
from tests.analysis.cache.test_dimension_runner_circuit_breaker import (
    _AllErrorsDispatcher,
    _SalvageDispatcher,
)


class TestBreakerScopedToDimension:
    """A trip ends the dimension; whether it ends the run depends on what
    the dimension managed before the streak.

    Shaka Player: 524 files analysed fine, then five binary ``.ts`` video
    segments failed in a row and the breaker cancelled all six dimensions.
    A dimension with successes behind it is looking at bad input, not a
    dead model, so the run-wide cancel is released once the dimension's
    pool has drained and the next dimension starts fresh. A dimension where
    nothing succeeded is the dead-endpoint case and the cancel stands.
    """

    def test_trip_after_successes_releases_the_run_wide_cancel(self, tmp_path, cache):
        from quodeq.shared import cancellation

        config, _src = _setup(tmp_path, {"a.py": "x"})
        config = replace(
            config, options=replace(config.options, failure_streak_threshold=3))
        ev = process_dimension_with_cache(
            config, "flexibility", 1, _make_ctx(),
            opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=_SalvageDispatcher(n_errors=3)),
        )
        assert ev is not None and ev.exit_reason == "failure_streak"
        assert not cancellation.is_cancelled(), (
            "one analysed file proves the model is alive; the next dimension must run"
        )
        assert cancellation.cancel_reason() is None

    def test_trip_with_no_successes_keeps_the_run_wide_cancel(self, tmp_path, cache):
        from quodeq.shared import cancellation

        config, _src = _setup(tmp_path, {"a.py": "x"})
        config = replace(
            config, options=replace(config.options, failure_streak_threshold=3))
        with pytest.raises(CircuitBreakerError):
            process_dimension_with_cache(
                config, "flexibility", 1, _make_ctx(),
                opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=_AllErrorsDispatcher(n_errors=3)),
            )
        assert cancellation.is_cancelled()
        assert cancellation.cancel_reason() == REASON_CIRCUIT_BREAKER
