"""Per-dim state transitions in the analysis loops."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.analysis._loops import run_per_dimension_loop, run_incremental_loop
from quodeq.analysis._types import RunConfig, AnalysisOptions
from quodeq.shared import cancellation
from quodeq.shared.dimensions_state import read_dimensions


@pytest.fixture(autouse=True)
def _reset_cancel():
    cancellation.reset()
    yield
    cancellation.reset()


def _mk_config(work_dir: Path):
    config = MagicMock()
    config.options.deadline_at = None
    config.options.incremental_file_filter = None
    config.options.skip_scoring = True
    config.options.incremental = False
    config.source_file_count = 10
    config.work_dir = work_dir
    config.src = work_dir
    return config


class TestPerDimensionLoopTransitions:
    def test_successful_dim_marked_done(self, tmp_path: Path):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=1)
        ev = MagicMock()
        process_fn = MagicMock(return_value=ev)

        run_per_dimension_loop(config, ["security"], ctx, process_fn=process_fn)

        states = read_dimensions(tmp_path)["dimensions"]
        assert states["security"]["state"] == "done"

    def test_exception_marks_incomplete_failed(self, tmp_path: Path):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=1)
        process_fn = MagicMock(side_effect=RuntimeError("boom"))

        run_per_dimension_loop(config, ["security"], ctx, process_fn=process_fn)

        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "incomplete"
        assert entry["reason"] == "failed_exception"

    def test_cancelled_marks_incomplete_signal(self, tmp_path: Path):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=1)

        def cancel_then_raise(*_a, **_kw):
            cancellation.request_cancel()
            raise RuntimeError("cancelled mid-flight")

        run_per_dimension_loop(
            config, ["security"], ctx,
            process_fn=MagicMock(side_effect=cancel_then_raise),
        )

        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "incomplete"
        assert entry["reason"] == "cancelled_signal"

    def test_ev_none_marks_incomplete(self, tmp_path: Path):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=1)
        process_fn = MagicMock(return_value=None)

        run_per_dimension_loop(config, ["security"], ctx, process_fn=process_fn)

        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "incomplete"

    def test_mixed_success_and_failure(self, tmp_path: Path):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=2)
        ev = MagicMock()

        def proc(_cfg, dim, _idx, _ctx):
            if dim == "security":
                return ev
            raise RuntimeError("boom")

        run_per_dimension_loop(
            config, ["security", "reliability"], ctx,
            process_fn=MagicMock(side_effect=proc),
        )

        states = read_dimensions(tmp_path)["dimensions"]
        assert states["security"]["state"] == "done"
        assert states["reliability"]["state"] == "incomplete"


class TestIncrementalLoopTransitions:
    def test_successful_dim_marked_done(self, tmp_path: Path, monkeypatch):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=1)
        ev = MagicMock()
        # Patch the incremental dispatcher so we don't go down the fallback path.
        monkeypatch.setattr(
            "quodeq.analysis._loops.run_dimension_incremental",
            lambda *a, **k: ev,
        )
        process_fn = MagicMock()
        log_result_fn = MagicMock()

        run_incremental_loop(
            config, ["security"], ctx,
            process_fn=process_fn, log_result_fn=log_result_fn,
        )

        assert read_dimensions(tmp_path)["dimensions"]["security"]["state"] == "done"

    def test_incremental_fallback_success_marks_done(
        self, tmp_path: Path, monkeypatch,
    ):
        # The incremental loop uses dataclasses.replace(config, ...) on the
        # fallback path, so config must be a real RunConfig dataclass instance.
        options = AnalysisOptions(
            deadline_at=None,
            incremental_file_filter=None,
            skip_scoring=True,
            incremental=False,
        )
        config = RunConfig(src=tmp_path, language="python", work_dir=tmp_path, options=options)
        ctx = MagicMock(total=1)
        ev = MagicMock()
        # Incremental fails, fallback succeeds.
        monkeypatch.setattr(
            "quodeq.analysis._loops.run_dimension_incremental",
            MagicMock(side_effect=RuntimeError("inc failed")),
        )
        process_fn = MagicMock(return_value=ev)
        log_result_fn = MagicMock()

        run_incremental_loop(
            config, ["security"], ctx,
            process_fn=process_fn, log_result_fn=log_result_fn,
        )

        assert read_dimensions(tmp_path)["dimensions"]["security"]["state"] == "done"

    def test_incremental_unexpected_exception_marks_incomplete(
        self, tmp_path: Path, monkeypatch,
    ):
        config = _mk_config(tmp_path)
        ctx = MagicMock(total=1)
        # Raise something that's NOT in the (OSError, KeyError, ValueError, RuntimeError) tuple.
        monkeypatch.setattr(
            "quodeq.analysis._loops.run_dimension_incremental",
            MagicMock(side_effect=KeyboardInterrupt("user ctrl-c")),
        )
        process_fn = MagicMock()
        log_result_fn = MagicMock()

        # KeyboardInterrupt would actually propagate -- but the bare Exception
        # handler catches `except Exception`, which doesn't include KeyboardInterrupt.
        # Use TypeError instead to test the bare handler.
        monkeypatch.setattr(
            "quodeq.analysis._loops.run_dimension_incremental",
            MagicMock(side_effect=TypeError("unexpected")),
        )

        run_incremental_loop(
            config, ["security"], ctx,
            process_fn=process_fn, log_result_fn=log_result_fn,
        )

        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "incomplete"
        assert entry["reason"] == "failed_exception"
