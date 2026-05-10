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


# ============================================================
# Run-dir resolution -- regression for dual-writer bug
# ============================================================
#
# Background: in production, RunLifecycleContext seeds dimensions.json at
# <run_dir>/dimensions.json. The analysis loop then writes state transitions
# to the SAME file. Pre-fix, the loop derived its target path from
# config.work_dir (which is <run_dir>/evidence/), producing TWO competing
# dimensions.json files -- the lifecycle's stayed at PENDING, the loop's
# advanced. The API read the lifecycle's, so dimStates was always wrong.
# These tests pin: when run_dir is set, the loop writes there, and the
# lifecycle and loop agree on the file.


class TestRunDirResolution:
    def test_loop_writes_to_run_dir_when_set(self, tmp_path: Path):
        from quodeq.analysis._loops import _run_dir_for

        run_dir = tmp_path / "run"
        evidence_dir = run_dir / "evidence"
        run_dir.mkdir()
        evidence_dir.mkdir()

        config = MagicMock()
        config.run_dir = run_dir
        config.work_dir = evidence_dir
        config.src = tmp_path / "src"
        assert _run_dir_for(config) == run_dir

    def test_falls_back_to_work_dir_when_run_dir_absent(self, tmp_path: Path):
        """Backward-compat for callers that haven't been migrated."""
        from quodeq.analysis._loops import _run_dir_for

        config = MagicMock()
        config.run_dir = None
        config.work_dir = tmp_path / "work"
        config.src = tmp_path / "src"
        assert _run_dir_for(config) == tmp_path / "work"

    def test_falls_back_to_src_when_neither_set(self, tmp_path: Path):
        from quodeq.analysis._loops import _run_dir_for

        config = MagicMock()
        config.run_dir = None
        config.work_dir = None
        config.src = tmp_path / "src"
        assert _run_dir_for(config) == tmp_path / "src"

    def test_loop_state_lands_where_lifecycle_seeds(self, tmp_path: Path):
        """End-to-end: lifecycle seeds + loop transitions write to ONE file."""
        from quodeq.shared.run_lifecycle import RunLifecycleContext
        from quodeq.shared.dimensions_state import DimState, read_dimensions

        run_dir = tmp_path / "run"
        evidence_dir = run_dir / "evidence"
        run_dir.mkdir()
        evidence_dir.mkdir()

        config = MagicMock()
        config.run_dir = run_dir
        config.work_dir = evidence_dir
        config.src = run_dir
        config.options.deadline_at = None
        config.options.incremental_file_filter = None
        config.options.skip_scoring = True
        config.options.incremental = False
        config.source_file_count = 1

        with RunLifecycleContext(run_dir, "ext-test", ["security"]):
            # Seed wrote PENDING to <run_dir>/dimensions.json.
            seed = read_dimensions(run_dir)["dimensions"]["security"]["state"]
            assert seed == "pending"

            # Now drive the loop -- transition to DONE.
            ev = MagicMock()
            ctx = MagicMock(total=1)
            run_per_dimension_loop(
                config, ["security"], ctx,
                process_fn=MagicMock(return_value=ev),
            )

        # The loop's DONE write hit the SAME file the lifecycle seeded.
        # Pre-fix: the loop wrote to <evidence_dir>/dimensions.json and the
        # outer file stayed at "pending".
        assert read_dimensions(run_dir)["dimensions"]["security"]["state"] == "done"
        assert not (evidence_dir / "dimensions.json").exists(), (
            "loop should not write a parallel dimensions.json in evidence/"
        )
