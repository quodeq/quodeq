"""Integration test: full API runner flow from provider config to JSONL evidence."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("instructor", reason="requires quodeq[api] extra")

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


def _mock_findings_model():
    """Build a mock Instructor response matching _Findings schema."""
    from quodeq.analysis._api_runner import _Findings, _Finding, _FindingType, _Severity

    return _Findings(findings=[
        _Finding(
            req="S-CON-3",
            t=_FindingType.violation,
            file="main.py",
            line=2,
            severity=_Severity.critical,
            w="Hardcoded password",
            reason="Password stored as plaintext string literal",
        ),
    ])


class TestApiIntegration:
    """End-to-end: run_analysis with API provider produces JSONL evidence."""

    def test_full_flow_ollama(self, source_repo, tmp_path):
        """Test with Ollama API via Instructor."""
        stream_file = tmp_path / "stream.json"
        jsonl_file = tmp_path / "evidence.jsonl"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_findings_model()

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis._api_runner.instructor") as mock_instructor:

            mock_cfg.return_value = {
                "ollama": {
                    "type": "api",
                    "model": "gemma4:26b",
                    "api_base": "http://localhost:11434/v1",
                }
            }
            mock_instructor.from_openai.return_value = mock_client
            mock_instructor.Mode.JSON = "json"

            cfg = AnalysisConfig(ai_cmd="ollama", jsonl_file=jsonl_file)
            run_analysis(
                work_dir=source_repo,
                prompt="Evaluate this code for security issues.",
                stream_file=stream_file,
                config=cfg,
            )

        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 1
        finding = json.loads(lines[0])
        assert finding["req"] == "S-CON-3"
        assert finding["t"] == "violation"
        assert finding["severity"] == "critical"
        assert stream_file.exists()

    def test_full_flow_openai_compatible(self, source_repo, tmp_path):
        """Test with OpenAI-compatible API via Instructor."""
        stream_file = tmp_path / "stream.json"
        jsonl_file = tmp_path / "evidence.jsonl"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_findings_model()

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis._api_runner.instructor") as mock_instructor:

            mock_cfg.return_value = {
                "openrouter": {
                    "type": "api",
                    "model": "anthropic/claude-sonnet-4",
                    "api_base": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                }
            }
            mock_instructor.from_openai.return_value = mock_client
            mock_instructor.Mode.JSON = "json"

            cfg = AnalysisConfig(ai_cmd="openrouter", jsonl_file=jsonl_file)
            run_analysis(
                work_dir=source_repo,
                prompt="Evaluate this code for security issues.",
                stream_file=stream_file,
                config=cfg,
            )

        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 1
        finding = json.loads(lines[0])
        assert finding["req"] == "S-CON-3"
