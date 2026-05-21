"""Integration tests — RunLifecycleContext is wired into _run_pipeline_with_cleanup."""
from __future__ import annotations

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
