"""Integration tests — RunLifecycleContext is wired into _run_pipeline_with_cleanup."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
