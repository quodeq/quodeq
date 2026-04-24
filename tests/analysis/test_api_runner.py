"""Tests for the Instructor-based API runner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

instructor = pytest.importorskip("instructor", reason="requires quodeq[api] extra")

from quodeq.analysis._api_runner import (
    run_api_analysis, ApiRunnerConfig,
    _Finding, _Findings, _FindingType, _Severity,
)


def _make_findings(*findings_data):
    """Build a _Findings model from (req, t, file, line, severity, w) tuples."""
    findings = []
    for req, t, file, line, severity, w in findings_data:
        findings.append(_Finding(
            req=req, t=_FindingType(t), file=file, line=line,
            severity=_Severity(severity), w=w, reason=f"Test reason for {req}",
        ))
    return _Findings(findings=findings)


@pytest.fixture()
def api_config():
    return ApiRunnerConfig(
        model="test-model",
        api_base="http://localhost:8000/v1",
        api_key="test-key",
    )


class TestRunApiAnalysis:
    """run_api_analysis calls LLM via Instructor and writes JSONL evidence."""

    def test_writes_jsonl_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        findings = _make_findings(
            ("M-MOD-1", "violation", "main.py", 5, "major", "Multiple responsibilities"),
            ("S-CON-3", "compliance", "utils.py", 1, "minor", "No hardcoded secrets"),
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(prompt="test prompt", jsonl_file=jsonl_file, config=api_config)

        assert jsonl_file.exists()
        lines = jsonl_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["req"] == "M-MOD-1"
        assert json.loads(lines[0])["t"] == "violation"
        assert json.loads(lines[1])["req"] == "S-CON-3"

    def test_passes_model_and_base_url(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        findings = _make_findings(("X-1", "violation", "a.py", 1, "minor", "test"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(prompt="test prompt", jsonl_file=jsonl_file, config=api_config)

            mock_openai.OpenAI.assert_called_once_with(
                base_url="http://localhost:8000/v1",
                api_key="test-key",
            )

    def test_handles_empty_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(prompt="test prompt", jsonl_file=jsonl_file, config=api_config)

        assert jsonl_file.exists()
        assert jsonl_file.read_text().strip() == ""

    def test_resolves_short_filenames(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        findings = _make_findings(("X-1", "violation", "app.py", 1, "minor", "test"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(
                prompt="test", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/myproject/app.py"],
            )

        finding = json.loads(jsonl_file.read_text().strip())
        assert finding["file"] == "src/myproject/app.py"

    def test_retries_configured(self, tmp_path, api_config):
        """Verify max_retries is passed to Instructor."""
        jsonl_file = tmp_path / "evidence.jsonl"
        findings = _make_findings(("X-1", "violation", "a.py", 1, "minor", "test"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(prompt="test", jsonl_file=jsonl_file, config=api_config)

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["max_retries"] == 1


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
