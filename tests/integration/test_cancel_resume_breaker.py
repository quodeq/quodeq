"""End-to-end: circuit breaker trip and scoring's incomplete-dim omission.

Split from test_cancel_resume.py. Shared scaffolding
(_ScriptedDispatcher, _setup_run, _make_ctx, _make_callbacks, etc.) lives
in tests/integration/_cancel_resume_fixtures.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.cache._failure_streak import CircuitBreakerError
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


class TestBreakerTrip:
    def test_breaker_raises_at_threshold(self, tmp_path: Path):
        """All errors with threshold=2 trips the breaker; CircuitBreakerError
        is raised and cancellation flag is set."""
        from quodeq.shared import cancellation

        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py"], threshold=2,
        )

        dispatcher = _ScriptedDispatcher(work_dir, behavior="all_errors")
        with pytest.raises(CircuitBreakerError):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache, dispatcher=dispatcher,
            )
        assert cancellation.is_cancelled()


class TestScoringSkipsIncompleteDim:
    def test_final_summary_omits_incomplete_dim(self, tmp_path: Path):
        """A run with one done dim + one incomplete dim writes a summary
        that includes only the done dim's report. The incomplete dim is
        NOT scored as 0 / NA."""
        from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence

        reports = tmp_path / "reports"
        run = reports / "proj" / "run-1"
        (run / "evidence").mkdir(parents=True)
        (run / "evaluation").mkdir(parents=True)

        # Both dims have evidence on disk (done dim from a prior fake run,
        # incomplete dim has partial findings + ok markers for two files).
        for dim in ("done_dim", "inc_dim"):
            jsonl = run / "evidence" / f"{dim}_evidence.jsonl"
            jsonl.write_text(
                json.dumps(_finding("a.py")) + "\n"
                + json.dumps(_ok_marker("a.py")) + "\n",
            )
            queue = run / "evidence" / f"{dim}_queue.json"
            queue.write_text(json.dumps({
                "version": 2, "pending": [],
                "taken": [{"files": ["a.py"], "agent": "a1", "ts": 0}],
            }))
        (reports / "proj" / "scan.json").write_text(
            json.dumps({"sourceFileCount": 1}),
        )

        # State: done_dim is DONE, inc_dim is INCOMPLETE.
        write_dim_state(run, "done_dim", DimState.PENDING)
        write_dim_state(run, "done_dim", DimState.RUNNING)
        write_dim_state(run, "done_dim", DimState.DONE)
        write_dim_state(run, "inc_dim", DimState.PENDING)
        write_dim_state(run, "inc_dim", DimState.RUNNING)
        write_dim_state(run, "inc_dim", DimState.INCOMPLETE,
                        reason="cancelled_by_user")

        _score_completed_evidence(str(reports), {
            "outputProject": "proj", "outputRunId": "run-1",
        })

        assert (run / "evaluation" / "done_dim.json").is_file()
        assert not (run / "evaluation" / "inc_dim.json").exists()
