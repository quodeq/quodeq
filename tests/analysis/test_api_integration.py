"""Integration test: full API runner flow from provider config to JSONL evidence."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

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


_FINDINGS_JSON = json.dumps({"findings": [
    {
        "req": "S-CON-3",
        "t": "violation",
        "file": "main.py",
        "line": 2,
        "severity": "critical",
        "w": "Hardcoded password",
        "snippet": "password = 'admin123'",
        "reason": "Password stored as plaintext string literal",
    },
]})


def _mock_openai_returning(content: str) -> MagicMock:
    """An openai.OpenAI(...) context manager whose chat.completions.create
    returns a raw response with `content`."""
    response = MagicMock(choices=[MagicMock(message=MagicMock(content=content))])
    client = MagicMock()
    client.chat.completions.create.return_value = response
    oa = MagicMock()
    oa.return_value.__enter__.return_value = client
    return oa


class TestApiIntegration:
    """End-to-end: run_analysis with API provider produces JSONL evidence."""

    def test_full_flow_ollama(self, source_repo, tmp_path):
        """Test with Ollama API via raw openai client."""
        stream_file = tmp_path / "stream.json"
        jsonl_file = tmp_path / "evidence.jsonl"

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis._api_runner.openai.OpenAI", _mock_openai_returning(_FINDINGS_JSON)):

            mock_cfg.return_value = {
                "ollama": {
                    "type": "api",
                    "model": "gemma4:26b",
                    "api_base": "http://localhost:11434/v1",
                }
            }

            cfg = AnalysisConfig(ai_cmd="ollama", jsonl_file=jsonl_file)
            run_analysis(
                work_dir=source_repo,
                prompt="Evaluate this code for security issues.",
                stream_file=stream_file,
                config=cfg,
            )

        assert jsonl_file.exists()
        all_lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings = [ln for ln in all_lines if "_marker" not in ln]
        assert len(findings) == 1
        assert findings[0]["req"] == "S-CON-3"
        assert findings[0]["t"] == "violation"
        assert findings[0]["severity"] == "critical"
        assert stream_file.exists()

    def test_full_flow_openai_compatible(self, source_repo, tmp_path):
        """Test with OpenAI-compatible API via raw openai client."""
        stream_file = tmp_path / "stream.json"
        jsonl_file = tmp_path / "evidence.jsonl"

        with patch("quodeq.analysis.subprocess.get_provider_configs") as mock_cfg, \
             patch("quodeq.analysis._api_runner.openai.OpenAI", _mock_openai_returning(_FINDINGS_JSON)):

            mock_cfg.return_value = {
                "openrouter": {
                    "type": "api",
                    "model": "anthropic/claude-sonnet-4",
                    "api_base": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                }
            }

            cfg = AnalysisConfig(ai_cmd="openrouter", jsonl_file=jsonl_file)
            run_analysis(
                work_dir=source_repo,
                prompt="Evaluate this code for security issues.",
                stream_file=stream_file,
                config=cfg,
            )

        assert jsonl_file.exists()
        all_lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings = [ln for ln in all_lines if "_marker" not in ln]
        assert len(findings) == 1
        assert findings[0]["req"] == "S-CON-3"
        assert findings[0]["t"] == "violation"
        assert stream_file.exists()
