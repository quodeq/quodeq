"""Tests for CLI pipeline execution — _build_manifest, _execute_pipeline, _save_manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestBuildManifest:
    def test_no_prescan_returns_none(self):
        from quodeq.cli import _build_manifest
        args = argparse.Namespace(no_prescan=True)
        result = _build_manifest(args, Path("/tmp"), MagicMock())
        assert result is None

    def test_detection_file_missing_returns_none(self):
        from quodeq.cli import _build_manifest
        args = argparse.Namespace(no_prescan=False)
        paths = MagicMock()
        paths.detection_file.exists.return_value = False
        result = _build_manifest(args, Path("/tmp"), paths)
        assert result is None


# ---------------------------------------------------------------------------
# _execute_pipeline tests
# ---------------------------------------------------------------------------

class TestExecutePipeline:
    @patch("quodeq._cli_evaluation.run")
    @patch("quodeq._cli_evaluation.write_text")
    def test_evidence_only_success(self, mock_write, mock_run, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=True, mode="numerical")
        mock_evidence = MagicMock()
        mock_evidence.to_evidence_dict.return_value = {"data": "test"}
        mock_run.return_value = mock_evidence
        config = MagicMock()
        config.language = "python"
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0
        mock_run.assert_called_once_with(config)

    @patch("quodeq._cli_evaluation.run")
    @patch("quodeq._cli_evaluation.write_text", side_effect=OSError("disk full"))
    def test_evidence_only_write_failure(self, mock_write, mock_run, tmp_path, capsys):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=True, mode="numerical")
        mock_evidence = MagicMock()
        mock_evidence.to_evidence_dict.return_value = {}
        mock_run.return_value = mock_evidence
        config = MagicMock()
        config.language = "python"
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 1
        assert "Failed to write" in capsys.readouterr().err

    @patch("quodeq._cli_evaluation.run_full")
    def test_full_pipeline_success(self, mock_run_full, tmp_path):
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.return_value = {"security": 8.5, "reliability": 7.0}
        config = MagicMock()
        config.options.skip_scoring = False
        result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
        assert result == 0

    @patch("quodeq._cli_evaluation.run_full")
    def test_pipeline_analysis_error(self, mock_run_full, tmp_path, capsys):
        # AnalysisError propagates from _execute_pipeline so that the outer
        # RunLifecycleContext can write state=failed.  The caller
        # (_run_pipeline_with_cleanup) is responsible for mapping it to exit 1.
        import pytest

        from quodeq.analysis.subprocess import AnalysisError
        from quodeq.cli import _execute_pipeline
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        evaluation_dir = tmp_path / "evaluation"
        evaluation_dir.mkdir()
        args = argparse.Namespace(evidence_only=False, mode="numerical")
        mock_run_full.side_effect = AnalysisError("AI failed")
        config = MagicMock()
        config.options.skip_scoring = False
        with pytest.raises(AnalysisError, match="AI failed"):
            _execute_pipeline(args, config, evidence_dir, evaluation_dir)


# ---------------------------------------------------------------------------
# _save_manifest tests
# ---------------------------------------------------------------------------

class TestSaveManifest:
    @patch("quodeq._cli_evaluation.manifest_to_dict")
    @patch("quodeq._cli_evaluation.write_text")
    def test_saves_when_manifest_exists(self, mock_write, mock_to_dict, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        mock_to_dict.return_value = {"targets": []}
        _save_manifest(manifest, tmp_path)
        mock_write.assert_called_once()

    def test_none_manifest_no_op(self, tmp_path):
        from quodeq.cli import _save_manifest
        _save_manifest(None, tmp_path)  # should not raise

    @patch("quodeq._cli_evaluation.manifest_to_dict")
    @patch("quodeq._cli_evaluation.write_text", side_effect=OSError("fail"))
    def test_os_error_silenced(self, mock_write, mock_to_dict, tmp_path):
        from quodeq.cli import _save_manifest
        manifest = MagicMock()
        mock_to_dict.return_value = {}
        _save_manifest(manifest, tmp_path)  # should not raise
