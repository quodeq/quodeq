"""Integration tests — deadline exit_reason wiring and the c88be50e regression.

Split from test_cli_lifecycle_integration.py. Shared helper
(_assert_partial_state_invariants) lives in tests/ci/_lifecycle_helpers.py.
"""
from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from quodeq.core.run.dimensions import DimState
from quodeq.data.fs.dimensions_state_store import write_dim_state
from quodeq.data.fs.run_status_store import read_status

from tests.ci._lifecycle_helpers import _assert_partial_state_invariants


def test_record_deadline_if_hit_tags_lifecycle_when_deadline_past(tmp_path: Path) -> None:
    """_record_deadline_if_hit must call set_exit_reason('deadline') when
    config.options.deadline_at is in the past (i.e. loop broke on deadline)."""
    import quodeq._cli_evaluation as cli
    from quodeq.analysis.run_lifecycle import RunLifecycleContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(
            options=SimpleNamespace(deadline_at=time.monotonic() - 1.0),
        )
        cli._record_deadline_if_hit(lifecycle, config)
        lifecycle.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] == "deadline"


def test_record_deadline_if_hit_noop_when_no_deadline(tmp_path: Path) -> None:
    """If config.options.deadline_at is None, the helper must NOT touch
    exit_reason — a clean run still finalizes with exit_reason=null."""
    import quodeq._cli_evaluation as cli
    from quodeq.analysis.run_lifecycle import RunLifecycleContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(options=SimpleNamespace(deadline_at=None))
        cli._record_deadline_if_hit(lifecycle, config)
        # Finish the declared dimension: a run that ends without scoring one
        # now reports incomplete_dimensions, which would mask what this asserts.
        write_dim_state(run_dir, "flex", DimState.RUNNING)
        write_dim_state(run_dir, "flex", DimState.DONE)
        lifecycle.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status.get("exit_reason") in (None, "")


def test_record_deadline_if_hit_noop_when_deadline_not_yet_reached(tmp_path: Path) -> None:
    """If the deadline is still in the future when the loops returned (clean
    completion before the budget), the helper must NOT tag exit_reason."""
    import quodeq._cli_evaluation as cli
    from quodeq.analysis.run_lifecycle import RunLifecycleContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(
            options=SimpleNamespace(deadline_at=time.monotonic() + 3600.0),
        )
        cli._record_deadline_if_hit(lifecycle, config)
        # Finish the declared dimension: a run that ends without scoring one
        # now reports incomplete_dimensions, which would mask what this asserts.
        write_dim_state(run_dir, "flex", DimState.RUNNING)
        write_dim_state(run_dir, "flex", DimState.DONE)
        lifecycle.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status.get("exit_reason") in (None, "")


def test_pipeline_records_deadline_exit_reason_when_budget_expired(tmp_path: Path) -> None:
    """End-to-end: when _execute_pipeline returns cleanly but the deadline
    set on config.options has already passed, the pipeline's status.json
    must show state=done AND exit_reason='deadline'."""
    import quodeq._cli_evaluation as cli

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    # Build a fake RunConfig with an already-past deadline. The pipeline's
    # loops would have broken out silently; our hook must catch that.
    fake_config = MagicMock()
    fake_config.options.deadline_at = time.monotonic() - 1.0
    fake_config.options.dimensions = ["flex"]

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config", return_value=fake_config), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(
            repo="local", max_duration=None, pool_budget=None,
        )
        inputs = cli.ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data=None)
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] == "deadline"


# ---------------------------------------------------------------------------
# c88be50e regression — partial-state invariants agree (Task 8)
# ---------------------------------------------------------------------------
#
# Symptom report: a flexibility run with --max-duration truncated at ~850 of
# 3037 files but the dashboard rendered it as "complete" (6.6/Adequate). On
# re-run, 123 of 280 findings vanished because only ~662 of 790 ok-marked
# files had a cache entry (the watcher.join timeout dropped ~16% of writes).
#
# Phase 1 closes the dashboard half of that gap by ensuring TWO partial-state
# signals agree end-to-end:
#
#   (a) lifecycle records exit_reason="deadline" (Task 5 + 6)
#   (b) the dimension Evidence reports files_read < source_file_count
#       (Task 4 — only files with a file_done="ok" marker count)
#
# Tasks 1–3 close the *finding-loss* half (synchronous cache writes); the
# regression for that is exercised by the cache test suite. This test pins
# the dashboard-visibility invariants together in one place so a future
# refactor can't silently re-introduce the "looks complete" bug.

def test_c88be50e_partial_state_invariants_agree(tmp_path: Path) -> None:
    """A deadline-truncated run must surface BOTH partial-state signals:
    status.json has exit_reason='deadline' AND _compute_files_read reports
    files_read < source_file_count for the dimension that broke on deadline.

    Scenario mirrors c88be50e in miniature: 5 input files, 1 pre-existing
    cache hit (carried through classify), the dispatcher gets to 2 ok
    completions and 1 error before the deadline trips and the remaining
    file never gets a marker.
    """
    import quodeq._cli_evaluation as cli
    from quodeq.analysis.run_lifecycle import RunLifecycleContext

    # --- Half (a): lifecycle records exit_reason="deadline" -----------------
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="c88be50e", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(
            options=SimpleNamespace(deadline_at=time.monotonic() - 1.0),
        )
        cli._record_deadline_if_hit(lifecycle, config)
        lifecycle.transition_to_finalizing()

    # --- Half (b): files_read reflects analyzed count, not input total ------
    _assert_partial_state_invariants(run_dir, tmp_path / "evidence")
