"""Integration tests — RunLifecycleContext is wired into _run_pipeline_with_cleanup."""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from quodeq.shared.run_status import read_status


def test_pipeline_writes_running_then_done(tmp_path: Path) -> None:
    """On clean exit the pipeline leaves status.json state=done."""
    import quodeq._cli_evaluation as cli

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None, "status.json must be written"
    assert status["state"] == "done"


def test_pipeline_writes_failed_on_exception(tmp_path: Path) -> None:
    """On exception the pipeline leaves status.json state=failed."""
    import quodeq._cli_evaluation as cli

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    def _boom(*a, **k):
        raise RuntimeError("pipeline failed")

    with patch.object(cli, "_execute_pipeline", side_effect=_boom), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        with pytest.raises(RuntimeError):
            cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status["state"] == "failed"
    assert status["exit_reason"] == "exception: RuntimeError"


def test_pipeline_writes_failed_on_domain_error(tmp_path: Path) -> None:
    """AnalysisError / EvaluationError propagate → status.json state=failed."""
    import quodeq._cli_evaluation as cli
    from quodeq.analysis.runner import EvaluationError

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    # Key difference vs existing tests: we patch the INNER pipeline function
    # (run_full / run) that raises EvaluationError, and let the production
    # _execute_pipeline / _run_pipeline_with_cleanup handle the propagation.
    with patch.object(cli, "_execute_pipeline", side_effect=EvaluationError("domain explosion")), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        # The wrapper should catch AnalysisError/EvaluationError, log, return 1.
        result = cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))
        assert result == 1

    from quodeq.shared.run_status import read_status
    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status["state"] == "failed"
    assert "EvaluationError" in status["exit_reason"]


# ---------------------------------------------------------------------------
# Deadline exit_reason wiring (Task 6)
# ---------------------------------------------------------------------------

def test_record_deadline_if_hit_tags_lifecycle_when_deadline_past(tmp_path: Path) -> None:
    """_record_deadline_if_hit must call set_exit_reason('deadline') when
    config.options.deadline_at is in the past (i.e. loop broke on deadline)."""
    import quodeq._cli_evaluation as cli
    from quodeq.shared.run_lifecycle import RunLifecycleContext

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
    from quodeq.shared.run_lifecycle import RunLifecycleContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(options=SimpleNamespace(deadline_at=None))
        cli._record_deadline_if_hit(lifecycle, config)
        lifecycle.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status.get("exit_reason") in (None, "")


def test_record_deadline_if_hit_noop_when_deadline_not_yet_reached(tmp_path: Path) -> None:
    """If the deadline is still in the future when the loops returned (clean
    completion before the budget), the helper must NOT tag exit_reason."""
    import quodeq._cli_evaluation as cli
    from quodeq.shared.run_lifecycle import RunLifecycleContext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="ext-test", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(
            options=SimpleNamespace(deadline_at=time.monotonic() + 3600.0),
        )
        cli._record_deadline_if_hit(lifecycle, config)
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
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
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

    Expected:
      - lifecycle status.json: state=done, exit_reason='deadline'
      - _compute_files_read = 3 (1 hit + 2 ok dispatches), source = 5
      - The two are written by different code paths; the regression is
        that both are present, not that either is present in isolation.
    """
    import quodeq._cli_evaluation as cli
    from quodeq.analysis.cache.dimension_helpers import ClassifyResult
    from quodeq.analysis.cache.dimension_runner import _compute_files_read
    from quodeq.shared.run_lifecycle import RunLifecycleContext

    # --- Half (a): lifecycle records exit_reason="deadline" -----------------
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with RunLifecycleContext(run_dir, job_id="c88be50e", dimensions=["flex"]) as lifecycle:
        config = SimpleNamespace(
            options=SimpleNamespace(deadline_at=time.monotonic() - 1.0),
        )
        cli._record_deadline_if_hit(lifecycle, config)
        lifecycle.transition_to_finalizing()

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] == "deadline", (
        "deadline-truncated run must tag exit_reason='deadline' so the "
        "dashboard can render a Partial badge instead of green-lighting "
        "an incomplete run as complete"
    )

    # --- Half (b): files_read reflects analyzed count, not input total ------
    # Five source files: a.py is a cache hit (already reproducible); b.py
    # and c.py dispatched and emitted file_done="ok" before the deadline;
    # d.py dispatched but errored; e.py never got a marker (worker
    # interrupted by the deadline).
    all_files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
    classify = ClassifyResult(
        cached_findings=[{"file": "a.py", "p": "P1", "line": 1, "t": "violation", "w": "x"}],
        misses=["b.py", "c.py", "d.py", "e.py"],
        miss_keys={f: f"key-{f}" for f in ["b.py", "c.py", "d.py", "e.py"]},
    )

    jsonl = tmp_path / "evidence" / "flex_evidence.jsonl"
    jsonl.parent.mkdir(parents=True)
    with jsonl.open("w") as out:
        # cached finding lands in the JSONL too (V2 runner mirrors hits in)
        out.write(json.dumps({"file": "a.py", "p": "P1", "line": 1, "t": "violation", "w": "x"}) + "\n")
        # b.py: one finding + ok marker
        out.write(json.dumps({"file": "b.py", "p": "P1", "line": 10, "t": "violation", "w": "y"}) + "\n")
        out.write(json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n")
        # c.py: no findings but ok marker (clean file)
        out.write(json.dumps({"_marker": "file_done", "file": "c.py", "status": "ok"}) + "\n")
        # d.py: error marker — must NOT count toward files_read
        out.write(json.dumps({"_marker": "file_done", "file": "d.py", "status": "error"}) + "\n")
        # e.py: no marker at all (deadline hit mid-worker) — must NOT count

    files_read = _compute_files_read(classify, jsonl, all_files)
    source_file_count = len(all_files)

    assert files_read == 3, (
        f"expected files_read=3 (1 hit + 2 ok dispatches), got {files_read}; "
        "the c88be50e symptom was files_read=len(input)=5, making coverage "
        "look 100% on a run that only completed 60% of files"
    )
    assert files_read < source_file_count, (
        f"deadline-truncated run must report files_read ({files_read}) < "
        f"source_file_count ({source_file_count}) — otherwise the dashboard "
        "computes coverage_pct=100 and renders a partial run as complete"
    )


# ---------------------------------------------------------------------------
# Provider/model wiring (Task 5)
# ---------------------------------------------------------------------------

def test_pipeline_records_provider_and_model_from_env(tmp_path: Path, monkeypatch) -> None:
    """status.json records the AI_PROVIDER/AI_MODEL the CLI ran with."""
    import quodeq._cli_evaluation as cli

    monkeypatch.setenv("AI_PROVIDER", "test-provider")
    monkeypatch.setenv("AI_MODEL", "test-model")

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None, "status.json must be written"
    assert status["ai_provider"] == "test-provider"
    assert status["ai_model"] == "test-model"


def test_pipeline_records_ai_cmd_as_provider(tmp_path: Path, monkeypatch) -> None:
    """status.json records AI_CMD as ai_provider when AI_CMD is set (not AI_PROVIDER).

    Locks in get_ai_cmd() semantics: the pipeline selects its provider via
    AI_CMD → AI_PROVIDER → default; the external path must record the same
    value as the internal path's options.ai_cmd.
    """
    import quodeq._cli_evaluation as cli

    monkeypatch.setenv("AI_CMD", "llamacpp")
    monkeypatch.setenv("AI_MODEL", "qwen3.6-27b")
    monkeypatch.delenv("AI_PROVIDER", raising=False)

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None, "status.json must be written"
    assert status["ai_provider"] == "llamacpp"
    assert status["ai_model"] == "qwen3.6-27b"
