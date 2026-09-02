"""End-to-end: cancel + resume + discard + token-out dispatch behavior.

Split from test_cancel_resume.py. Shared scaffolding
(_ScriptedDispatcher, _setup_run, _make_ctx, _make_callbacks, etc.) lives
in tests/integration/_cancel_resume_fixtures.py.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state

from tests.integration._cancel_resume_fixtures import (  # noqa: F401 -- _reset_cancel is a pytest fixture
    _ScriptedDispatcher,
    _finding,
    _make_callbacks,
    _make_ctx,
    _ok_marker,
    _reset_cancel,
    _setup_run,
)


class TestResumeAfterCancel:
    def test_completed_files_cached_uncompleted_redispatched(self, tmp_path: Path):
        """Cancel mid-dim. First run caches files completed before cancel.
        Second run sees those as hits and only re-dispatches the rest."""
        from quodeq.shared import cancellation

        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py", "d.py"],
        )

        # Run 1: cancel after 2 files complete.
        d1 = _ScriptedDispatcher(work_dir, behavior="first_two_ok_then_cancel")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d1,
        )
        # First run dispatched all 4 files into the pool (cancel happens AFTER
        # the dispatcher returns). Two have ok markers, two don't.
        assert d1.calls[0] == {"a.py", "b.py", "c.py", "d.py"}

        # Reset cancellation so the second run can proceed.
        cancellation.reset()

        # Run 2: clean dispatch of remaining files only.
        d2 = _ScriptedDispatcher(work_dir, behavior="ok_all")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d2,
        )
        # Second run only dispatched the two files that didn't get an ok marker.
        assert d2.calls[0] == {"c.py", "d.py"}


class TestDiscardForcesFullRedispatch:
    def test_discard_wipes_cache_so_second_run_dispatches_all(self, tmp_path: Path):
        """After cancel, an explicit discard wipes the V2 cache for the
        incomplete dim. Second run sees no hits and dispatches every file."""
        from quodeq.shared import cancellation
        from quodeq.services.evaluation_mixin import _discard_run_state

        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py", "d.py"],
        )

        # Layout so _discard_run_state can find the run.
        # reports_dir/<project>/<run-id>/evidence/
        reports_dir = tmp_path / "reports"
        run_dir = reports_dir / "proj" / "run-1"
        (run_dir / "evidence").mkdir(parents=True)
        (run_dir / "evaluation").mkdir(parents=True)
        # Repoint config's work_dir to the run dir so the dispatch-keys
        # sidecar and JSONL land where the discard path looks.
        config = replace(config, work_dir=run_dir / "evidence")

        d1 = _ScriptedDispatcher(run_dir / "evidence", behavior="first_two_ok_then_cancel")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d1,
        )
        cancellation.reset()

        # Mark the dim as incomplete in dimensions.json, then discard.
        write_dim_state(run_dir, "security", DimState.PENDING)
        write_dim_state(run_dir, "security", DimState.RUNNING)
        write_dim_state(run_dir, "security", DimState.INCOMPLETE,
                        reason="cancelled_by_user")

        # The dispatch-keys sidecar exists at evidence/security_dispatch_keys.json
        # (written by S1.E's dim runner). Confirm before invoking discard.
        assert (run_dir / "evidence" / "security_dispatch_keys.json").is_file()

        _discard_run_state(str(reports_dir), {
            "outputProject": "proj", "outputRunId": "run-1",
        }, cache=cache)

        # JSONL wiped; cache entries for both ok files removed.
        assert not (run_dir / "evidence" / "security_evidence.jsonl").exists()

        # Run 2 dispatches every file (no cache hits).
        d2 = _ScriptedDispatcher(run_dir / "evidence", behavior="ok_all")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d2,
        )
        assert d2.calls[0] == {"a.py", "b.py", "c.py", "d.py"}


class TestTokenOutMidFile:
    def test_error_marked_file_redispatched_ok_files_cached(self, tmp_path: Path):
        """Worker emits an error marker for one file, ok for the rest. Only
        the error-marked file is re-dispatched on the next run."""
        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py"],
        )

        d1 = _ScriptedDispatcher(work_dir, behavior="first_one_token_limit")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d1,
        )

        # Second run: only the error-marked file should re-dispatch.
        d2 = _ScriptedDispatcher(work_dir, behavior="ok_all")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d2,
        )
        assert d2.calls[0] == {"a.py"}


class TestCrashPathPreservesLikeCancel:
    def test_exception_treated_as_preserve(self, tmp_path: Path):
        """A non-cancel exception during dispatch leaves ok-marked files
        cached for the next run (auto-preserve). Mirrors the cancel path."""
        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py"],
        )

        class _CrashAfterTwo:
            def __init__(self):
                self.calls = []

            def __call__(self, config, dim_id, idx, ctx, callbacks, **_):
                self.calls.append(sorted(config.options.incremental_file_filter or set()))
                jsonl = (config.work_dir or config.src) / f"{dim_id}_evidence.jsonl"
                with jsonl.open("a") as out:
                    out.write(json.dumps(_finding("a.py")) + "\n")
                    out.write(json.dumps(_ok_marker("a.py")) + "\n")
                    out.write(json.dumps(_finding("b.py")) + "\n")
                    out.write(json.dumps(_ok_marker("b.py")) + "\n")
                raise RuntimeError("crashed mid-dispatch")

        d1 = _CrashAfterTwo()
        with pytest.raises(RuntimeError):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache, dispatcher=d1,
            )

        # Second run: a.py and b.py were cached (had ok markers); c.py
        # was never reached, so it dispatches.
        d2 = _ScriptedDispatcher(work_dir, behavior="ok_all")
        process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache, dispatcher=d2,
        )
        assert d2.calls[0] == {"c.py"}
