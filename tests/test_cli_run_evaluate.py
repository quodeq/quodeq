"""Tests for CLI run_evaluate() — prereqs, input resolution, pipeline dispatch."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch


class TestRunEvaluate:
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs", side_effect=RuntimeError("no claude"))
    def test_prereqs_failure(self, mock_prereqs, capsys):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1
        assert "no claude" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation._resolve_evaluation_inputs", return_value=None)
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs")
    def test_resolve_inputs_none(self, mock_prereqs, mock_resolve):
        from quodeq.cli import run_evaluate
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 1

    @patch("quodeq._cli_evaluation._run_pipeline_with_cleanup", return_value=0)
    @patch("quodeq._cli_evaluation._setup_run_dirs")
    @patch("quodeq._cli_evaluation._resolve_evaluation_inputs")
    @patch("quodeq._cli_evaluation.check_evaluate_prereqs")
    def test_successful_evaluate(self, mock_prereqs, mock_resolve, mock_dirs, mock_pipeline):
        from quodeq.cli import ResolvedInputs, run_evaluate
        mock_resolve.return_value = ResolvedInputs(
            src=Path("/tmp/repo"), language="python", manifest=None, dims_data={}
        )
        mock_dirs.return_value = (Path("/tmp/out"), Path("/tmp/ev"), Path("/tmp/eval"))
        args = argparse.Namespace()
        result = run_evaluate(args)
        assert result == 0
        mock_pipeline.assert_called_once()
