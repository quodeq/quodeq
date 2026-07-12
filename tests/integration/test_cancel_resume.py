"""End-to-end: cancel + resume + discard + token-out + breaker.

Composes the building blocks (per-file markers, per-dim state, V2 cache,
dispatch-keys sidecar, discard wipe, circuit breaker) by driving the dim
runner with a programmable fake dispatcher and the real cache backend.

No real subprocesses, no real network. The fake dispatcher writes a
scripted finding-and-marker stream into the dim's evidence JSONL the
same way the production pool does, so the cache layer, dim-state
writer, and breaker all see realistic input.
"""
from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.cache._failure_streak import CircuitBreakerError
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence
from quodeq.shared import cancellation
from quodeq.shared.dimensions_state import DimState, read_dimensions, write_dim_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_cancel():
    cancellation.reset()
    yield
    cancellation.reset()


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _make_config(
    src: Path, *, work_dir: Path,
    file_names: list[str],
    threshold: int = 5,
) -> RunConfig:
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=work_dir,
        options=AnalysisOptions(
            subagent_model="test-model",
            failure_streak_threshold=threshold,
        ),
        manifest=_make_manifest(file_names),
    )


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01",
        template="",
        subagent_template="",
        total=1,
    )


def _make_callbacks() -> DimensionCallbacks:
    from quodeq.analysis._dimension_steps import (
        _build_dimension_prompt,
        _parse_dimension_evidence,
        _run_dimension_analysis,
    )
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )


def _make_dummy_evidence(*, files_read: int) -> Evidence:
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=files_read, files_read=files_read,
        coverage_pct=100.0, principles={},
    )


def _setup_run(tmp_path: Path, files: list[str], threshold: int = 5):
    src = tmp_path / "src"
    src.mkdir()
    for name in files:
        (src / name).write_text(f"# {name}\n")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    cache = LocalFileBackend(root=tmp_path / "cache")
    config = _make_config(src, work_dir=work_dir, file_names=files, threshold=threshold)
    return config, src, work_dir, cache


def _ok_marker(f: str) -> dict:
    return {"_marker": "file_done", "file": f, "status": "ok"}


def _err_marker(f: str, reason: str = "token_limit") -> dict:
    return {"_marker": "file_done", "file": f, "status": "error", "reason": reason}


def _finding(f: str) -> dict:
    return {"file": f, "line": 1, "t": "violation", "severity": "minor",
            "w": f"v-{f}", "reason": "r", "req": "X-1",
            "p": "Modularity", "d": "maintainability"}


# ---------------------------------------------------------------------------
# Programmable fake dispatcher
# ---------------------------------------------------------------------------

class _ScriptedDispatcher:
    """Writes a caller-defined sequence of JSONL lines for each call."""

    def __init__(self, work_dir: Path, *, behavior: str = "ok_all"):
        self._work_dir = work_dir
        self._behavior = behavior
        self.calls: list[set[str]] = []

    def __call__(
        self, config: RunConfig, dim_id: str, idx: int, ctx, callbacks,
    ) -> Evidence | None:
        files = sorted(config.options.incremental_file_filter or set())
        self.calls.append(set(files))
        jsonl = (config.work_dir or config.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            for entry in self._script(files):
                out.write(json.dumps(entry) + "\n")
        # No sleep: the breaker does a final scan when the runner signals stop
        # (see FailureStreakWatcher._run), so a trip is detected deterministically
        # once dispatch returns -- it no longer depends on a poll landing during
        # dispatch. The old fixed sleep was a slow-runner flake ("DID NOT RAISE
        # CircuitBreakerError" on macos-latest).
        return _make_dummy_evidence(files_read=len(files))

    def _script(self, files: list[str]):
        if self._behavior == "ok_all":
            for f in files:
                yield _finding(f)
                yield _ok_marker(f)
        elif self._behavior == "first_two_ok_then_cancel":
            for f in files[:2]:
                yield _finding(f)
                yield _ok_marker(f)
            cancellation.request_cancel()
        elif self._behavior == "first_one_token_limit":
            yield _finding(files[0])
            yield _err_marker(files[0], "token_limit")
            for f in files[1:]:
                yield _finding(f)
                yield _ok_marker(f)
        elif self._behavior == "all_errors":
            for f in files:
                yield _err_marker(f, "token_limit")
        else:
            raise ValueError(f"unknown behavior: {self._behavior}")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

class TestResumeAfterCancel:
    def test_completed_files_cached_uncompleted_redispatched(self, tmp_path: Path):
        """Cancel mid-dim. First run caches files completed before cancel.
        Second run sees those as hits and only re-dispatches the rest."""
        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py", "d.py"],
        )

        # Run 1: cancel after 2 files complete.
        d1 = _ScriptedDispatcher(work_dir, behavior="first_two_ok_then_cancel")
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d1,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )
        # First run dispatched all 4 files into the pool (cancel happens AFTER
        # the dispatcher returns). Two have ok markers, two don't.
        assert d1.calls[0] == {"a.py", "b.py", "c.py", "d.py"}

        # Reset cancellation so the second run can proceed.
        cancellation.reset()

        # Run 2: clean dispatch of remaining files only.
        d2 = _ScriptedDispatcher(work_dir, behavior="ok_all")
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d2,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )
        # Second run only dispatched the two files that didn't get an ok marker.
        assert d2.calls[0] == {"c.py", "d.py"}


class TestDiscardForcesFullRedispatch:
    def test_discard_wipes_cache_so_second_run_dispatches_all(self, tmp_path: Path):
        """After cancel, an explicit discard wipes the V2 cache for the
        incomplete dim. Second run sees no hits and dispatches every file."""
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
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d1,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
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

        with patch(
            "quodeq.services.evaluation_mixin._open_cache",
            lambda: cache,
        ):
            _discard_run_state(str(reports_dir), {
                "outputProject": "proj", "outputRunId": "run-1",
            })

        # JSONL wiped; cache entries for both ok files removed.
        assert not (run_dir / "evidence" / "security_evidence.jsonl").exists()

        # Run 2 dispatches every file (no cache hits).
        d2 = _ScriptedDispatcher(run_dir / "evidence", behavior="ok_all")
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d2,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
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
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d1,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        # Second run: only the error-marked file should re-dispatch.
        d2 = _ScriptedDispatcher(work_dir, behavior="ok_all")
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d2,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )
        assert d2.calls[0] == {"a.py"}


class TestBreakerTrip:
    def test_breaker_raises_at_threshold(self, tmp_path: Path):
        """All errors with threshold=2 trips the breaker; CircuitBreakerError
        is raised and cancellation flag is set."""
        config, src, work_dir, cache = _setup_run(
            tmp_path, ["a.py", "b.py", "c.py"], threshold=2,
        )

        dispatcher = _ScriptedDispatcher(work_dir, behavior="all_errors")
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            with pytest.raises(CircuitBreakerError):
                process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
                )
        assert cancellation.is_cancelled()


class TestScoringSkipsIncompleteDim:
    def test_final_summary_omits_incomplete_dim(self, tmp_path: Path):
        """A run with one done dim + one incomplete dim writes a summary
        that includes only the done dim's report. The incomplete dim is
        NOT scored as 0 / NA."""
        from quodeq.services.evaluation_mixin import _score_completed_evidence

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

            def __call__(self, config, dim_id, idx, ctx, callbacks):
                self.calls.append(sorted(config.options.incremental_file_filter or set()))
                jsonl = (config.work_dir or config.src) / f"{dim_id}_evidence.jsonl"
                with jsonl.open("a") as out:
                    out.write(json.dumps(_finding("a.py")) + "\n")
                    out.write(json.dumps(_ok_marker("a.py")) + "\n")
                    out.write(json.dumps(_finding("b.py")) + "\n")
                    out.write(json.dumps(_ok_marker("b.py")) + "\n")
                raise RuntimeError("crashed mid-dispatch")

        d1 = _CrashAfterTwo()
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d1,
        ):
            with pytest.raises(RuntimeError):
                process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
                )

        # Second run: a.py and b.py were cached (had ok markers); c.py
        # was never reached, so it dispatches.
        d2 = _ScriptedDispatcher(work_dir, behavior="ok_all")
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d2,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )
        assert d2.calls[0] == {"c.py"}
