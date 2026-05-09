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
            severity=_Severity(severity), w=w,
            snippet=f"line for {req}",
            reason=f"Test reason for {req}",
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

        lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings = [ln for ln in lines if "_marker" not in ln]
        assert len(findings) == 1
        assert findings[0]["file"] == "src/myproject/app.py"

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


class TestMarkerContract:
    """API runner emits file_done markers so the V2 cache can record
    completion. The CLI/MCP path emits these via the agent calling
    `mark_file_done`; the API path is one-shot and emits them itself
    after a clean Instructor return.

    Regression: before this, the API runner wrote findings to JSONL
    directly, bypassing FindingsRouter and the marker contract. Cache
    saw zero ok_files for every API run, so cancel-then-restart never
    benefited from prior work. See spec/cancellation design v2.
    """

    def _read_jsonl(self, jsonl_file: Path) -> list[dict]:
        return [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]

    def _findings_only(self, lines: list[dict]) -> list[dict]:
        return [ln for ln in lines if "_marker" not in ln]

    def _markers(self, lines: list[dict]) -> list[dict]:
        return [ln for ln in lines if ln.get("_marker") == "file_done"]

    def test_clean_call_emits_ok_marker_per_source_file(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        findings = _make_findings(
            ("M-MOD-1", "violation", "src/a.py", 5, "major", "x"),
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/a.py", "src/b.py", "src/c.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        marked_files = {m["file"] for m in markers}
        assert marked_files == {"src/a.py", "src/b.py", "src/c.py"}
        assert all(m["status"] == "ok" for m in markers)

    def test_clean_call_with_zero_findings_still_marks_files(self, tmp_path, api_config):
        """A clean file (no findings) is still completed analysis -- mark it ok."""
        jsonl_file = tmp_path / "evidence.jsonl"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/clean.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        assert self._findings_only(lines) == []
        markers = self._markers(lines)
        assert len(markers) == 1
        assert markers[0]["file"] == "src/clean.py"
        assert markers[0]["status"] == "ok"

    def test_salvaged_response_does_not_emit_markers(self, tmp_path, api_config):
        """When the response was malformed and we salvaged partial findings,
        we don't know which files were actually analyzed end-to-end. Don't
        lie about completion -- leave markers off so the next run re-runs."""
        jsonl_file = tmp_path / "evidence.jsonl"

        mock_client = MagicMock()
        # Force the salvage path: Instructor raises, but the raw exception
        # message contains a single salvageable finding object.
        salvage_payload = json.dumps({
            "req": "X-1", "t": "violation", "file": "src/a.py", "line": 1,
            "severity": "minor", "w": "x", "snippet": "code", "reason": "r",
        })
        mock_client.chat.completions.create.side_effect = RuntimeError(salvage_payload)

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=["src/a.py", "src/b.py"],
            )

        lines = self._read_jsonl(jsonl_file)
        # Salvaged finding(s) are still written.
        assert any(ln.get("req") == "X-1" for ln in self._findings_only(lines))
        # But NO markers -- cancel-then-restart will re-run all files.
        assert self._markers(lines) == []

    def test_no_source_files_no_markers(self, tmp_path, api_config):
        """Backward-compat: callers that don't pass source_file_paths get
        finding writes only -- the CLI dim runner is the typical caller and
        that's expected when the whole-dim file list isn't known here."""
        jsonl_file = tmp_path / "evidence.jsonl"
        findings = _make_findings(("X-1", "violation", "a.py", 1, "minor", "x"))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"

            run_api_analysis(
                prompt="t", jsonl_file=jsonl_file, config=api_config,
                source_file_paths=None,
            )

        lines = self._read_jsonl(jsonl_file)
        assert self._markers(lines) == []
        assert len(self._findings_only(lines)) == 1


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
