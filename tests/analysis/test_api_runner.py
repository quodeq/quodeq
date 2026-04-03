"""Tests for the OpenAI SDK-based API runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._api_runner import run_api_analysis, ApiRunnerConfig


@pytest.fixture()
def mock_openai_response():
    """Create a mock OpenAI chat completion response."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "findings": [
            {
                "req": "M-MOD-1",
                "t": "violation",
                "file": "main.py",
                "line": 5,
                "severity": "major",
                "w": "Multiple responsibilities",
                "reason": "Module mixes IO and business logic",
            },
            {
                "req": "S-CON-3",
                "t": "compliance",
                "file": "utils.py",
                "line": 1,
                "severity": "minor",
                "w": "No hardcoded secrets",
                "reason": "No secrets found in file",
            },
        ]
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@pytest.fixture()
def api_config():
    """Create a minimal ApiRunnerConfig."""
    return ApiRunnerConfig(
        model="test-model",
        api_base="http://localhost:11434/v1",
        api_key="test-key",
    )


class TestRunApiAnalysis:
    """run_api_analysis calls OpenAI SDK and writes JSONL evidence."""

    def test_writes_jsonl_findings(self, tmp_path, mock_openai_response, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        (tmp_path / "main.py").write_text("x = 1\n")

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 2
        finding = json.loads(lines[0])
        assert finding["req"] == "M-MOD-1"
        assert finding["t"] == "violation"

    def test_passes_model_and_base_url(self, tmp_path, mock_openai_response, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

            mock_openai.OpenAI.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="test-key",
            )
            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["model"] == "test-model"

    def test_handles_empty_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({"findings": []})
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

        assert jsonl_file.exists()
        assert jsonl_file.read_text().strip() == ""

    def test_handles_malformed_json_response(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        mock_choice = MagicMock()
        mock_choice.message.content = "This is not JSON at all"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_client

            with pytest.raises(ValueError, match="parse"):
                run_api_analysis(
                    prompt="test prompt",
                    jsonl_file=jsonl_file,
                    config=api_config,
                )

    def test_requests_json_response_format(self, tmp_path, mock_openai_response, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"

        with patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_openai_response
            mock_openai.OpenAI.return_value = mock_client

            run_api_analysis(
                prompt="test prompt",
                jsonl_file=jsonl_file,
                config=api_config,
            )

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["response_format"] == {"type": "json_object"}


class TestApiRunnerConfig:
    """ApiRunnerConfig dataclass."""

    def test_defaults(self):
        cfg = ApiRunnerConfig(model="test", api_base="http://localhost/v1")
        assert cfg.api_key == ""
        assert cfg.temperature == 0.1
        assert cfg.max_tokens is None

    def test_custom_values(self):
        cfg = ApiRunnerConfig(
            model="gpt-4o",
            api_base="https://api.openai.com/v1",
            api_key="sk-...",
            temperature=0.0,
            max_tokens=4096,
        )
        assert cfg.temperature == 0.0
        assert cfg.max_tokens == 4096
