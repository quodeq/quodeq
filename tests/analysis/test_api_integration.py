"""Integration test: full API runner flow from provider config to JSONL evidence."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subprocess import run_analysis
from quodeq.analysis._config import AnalysisConfig


@pytest.fixture()
def source_repo(tmp_path):
    """Create a minimal source repo for evaluation."""
    src = tmp_path / "repo"
    src.mkdir()
    (src / "main.py").write_text(
        "import os\n"
        "password = 'hunter2'\n"
        "def run():\n"
        "    os.system(password)\n"
    )
    return src


class TestApiIntegration:
    """End-to-end: run_analysis with API provider produces JSONL evidence."""

    def test_full_flow(self, source_repo, tmp_path):
        stream_file = tmp_path / "stream.json"
        jsonl_file = tmp_path / "evidence.jsonl"

        mock_findings = {
            "findings": [
                {
                    "req": "S-CON-3",
                    "t": "violation",
                    "file": "main.py",
                    "line": 2,
                    "severity": "critical",
                    "w": "Hardcoded password",
                    "reason": "Password stored as plaintext string literal",
                },
            ]
        }

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(mock_findings)
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis._api_runner.openai") as mock_openai:

            mock_cfg.return_value = {
                "ollama": {
                    "type": "api",
                    "model": "llama3.1",
                    "api_base": "http://localhost:11434/v1",
                }
            }

            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            cfg = AnalysisConfig(ai_cmd="ollama", jsonl_file=jsonl_file)
            run_analysis(
                work_dir=source_repo,
                prompt="Evaluate this code for security issues.",
                stream_file=stream_file,
                config=cfg,
            )

        # Verify JSONL evidence was produced
        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 1
        finding = json.loads(lines[0])
        assert finding["req"] == "S-CON-3"
        assert finding["t"] == "violation"
        assert finding["severity"] == "critical"

        # Verify stream file was created (for downstream checks)
        assert stream_file.exists()
