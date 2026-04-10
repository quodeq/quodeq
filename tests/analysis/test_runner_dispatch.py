"""Tests for runner dispatch based on provider type."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subprocess import run_analysis
from quodeq.analysis._config import AnalysisConfig


class TestRunnerDispatch:
    """run_analysis routes to CLI or API runner based on provider config type."""

    def test_cli_type_uses_subprocess(self, tmp_path):
        """Provider with type=cli should call the subprocess runner."""
        stream_file = tmp_path / "stream.json"
        stream_file.touch()
        cfg = AnalysisConfig(ai_cmd="claude")

        with patch("quodeq.analysis.subprocess._run_cli_analysis") as mock_cli:
            mock_cli.return_value = None
            run_analysis(
                work_dir=tmp_path, prompt="test", stream_file=stream_file, config=cfg,
            )
            mock_cli.assert_called_once()

    def test_api_type_uses_api_runner(self, tmp_path):
        """Provider with type=api should call the API runner."""
        stream_file = tmp_path / "stream.json"
        stream_file.touch()
        jsonl_file = tmp_path / "evidence.jsonl"
        cfg = AnalysisConfig(ai_cmd="ollama", jsonl_file=jsonl_file)

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis.subprocess._run_api_analysis_bridge") as mock_api:
            mock_cfg.return_value = {
                "ollama": {
                    "type": "api",
                    "model": "llama3.1",
                    "api_base": "http://localhost:11434/v1",
                }
            }
            mock_api.return_value = None
            run_analysis(
                work_dir=tmp_path, prompt="test", stream_file=stream_file, config=cfg,
            )
            mock_api.assert_called_once()

    def test_unknown_provider_defaults_to_cli(self, tmp_path):
        """Unknown providers should fall back to CLI runner."""
        stream_file = tmp_path / "stream.json"
        stream_file.touch()
        cfg = AnalysisConfig(ai_cmd="unknown-tool")

        with patch("quodeq.analysis.subprocess._run_cli_analysis") as mock_cli:
            mock_cli.return_value = None
            run_analysis(
                work_dir=tmp_path, prompt="test", stream_file=stream_file, config=cfg,
            )
            mock_cli.assert_called_once()
