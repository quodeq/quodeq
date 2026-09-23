"""Tests for the API runner: JSONL evidence writing and the file_done marker contract."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis._api_call import _LOCAL_TIMEOUT
from quodeq.analysis._api_runner import ApiAnalysisRequest, call_api, run_api_analysis

from ._api_runner_helpers import (
    _make_findings_json,
    _mock_raw_client,
    _mock_raw_client_finish,
)


class TestRunApiAnalysis:
    """run_api_analysis calls LLM via raw OpenAI client and writes JSONL evidence."""

    def test_writes_jsonl_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(
            ("M-MOD-1", "violation", "main.py", 5, "major", "Multiple responsibilities"),
            ("S-CON-3", "compliance", "utils.py", 1, "minor", "No hardcoded secrets"),
        )
        raw_client = _mock_raw_client(content)

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(prompt="test prompt", jsonl_file=jsonl_file),
                config=api_config,
            )

        assert jsonl_file.exists()
        lines = [ln for ln in jsonl_file.read_text().strip().split("\n") if ln]
        finding_lines = [json.loads(ln) for ln in lines if "_marker" not in ln]
        assert len(finding_lines) == 2
        assert finding_lines[0]["req"] == "M-MOD-1"
        assert finding_lines[0]["t"] == "violation"
        assert finding_lines[1]["req"] == "S-CON-3"

    def test_passes_model_and_base_url(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = _mock_raw_client('{"findings":[]}')

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(prompt="test prompt", jsonl_file=jsonl_file),
                config=api_config,
            )

            mock_oa.assert_called_once_with(
                base_url="http://localhost:8000/v1",
                api_key="test-key",
                timeout=_LOCAL_TIMEOUT,
                max_retries=0,
            )

    def test_handles_empty_findings(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = _mock_raw_client('{"findings":[]}')

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(prompt="test prompt", jsonl_file=jsonl_file),
                config=api_config,
            )

        assert jsonl_file.exists()
        # Only markers (if any), no findings
        lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings_only = [ln for ln in lines if "_marker" not in ln]
        assert findings_only == []

    def test_resolves_short_filenames(self, tmp_path, api_config):
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("X-1", "violation", "app.py", 1, "minor", "test"))
        raw_client = _mock_raw_client(content)

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="test", jsonl_file=jsonl_file,
                    source_file_paths=["src/myproject/app.py"],
                ),
                config=api_config,
            )

        lines = [json.loads(ln) for ln in jsonl_file.read_text().splitlines() if ln.strip()]
        findings = [ln for ln in lines if "_marker" not in ln]
        assert len(findings) == 1
        assert findings[0]["file"] == "src/myproject/app.py"

    def test_client_disables_sdk_retries(self, tmp_path, api_config):
        with patch("openai.OpenAI") as mock_oa:
            client = MagicMock()
            client.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content='{"findings":[]}'))]
            )
            mock_oa.return_value.__enter__.return_value = client
            call_api("prompt", api_config)
        assert mock_oa.call_args.kwargs["max_retries"] == 0


class TestMarkerContract:
    """API runner emits file_done markers so the V2 cache can record
    completion. The CLI/MCP path emits these via the agent calling
    `mark_file_done`; the API path is one-shot and emits them itself
    after a clean LLM return.

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
        content = _make_findings_json(("M-MOD-1", "violation", "src/a.py", 5, "major", "x"))
        raw_client = _mock_raw_client(content)

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="t", jsonl_file=jsonl_file,
                    source_file_paths=["src/a.py", "src/b.py", "src/c.py"],
                ),
                config=api_config,
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        marked_files = {m["file"] for m in markers}
        assert marked_files == {"src/a.py", "src/b.py", "src/c.py"}
        assert all(m["status"] == "ok" for m in markers)

    def test_clean_call_with_zero_findings_still_marks_files(self, tmp_path, api_config):
        """A clean file (no findings) is still completed analysis -- mark it ok."""
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = _mock_raw_client('{"findings":[]}')

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="t", jsonl_file=jsonl_file,
                    source_file_paths=["src/clean.py"],
                ),
                config=api_config,
            )

        lines = self._read_jsonl(jsonl_file)
        assert self._findings_only(lines) == []
        markers = self._markers(lines)
        assert len(markers) == 1
        assert markers[0]["file"] == "src/clean.py"
        assert markers[0]["status"] == "ok"

    def test_network_error_emits_error_markers(self, tmp_path, api_config):
        """When the model call fails (was_lossy=True), emit an 'error' marker
        for every file in the batch.

        This makes the failure visible to the failure-streak circuit breaker
        and the post-run model-reachability guard, so an unreachable/broken
        model fails the run loudly instead of silently producing zero findings.
        'error' markers are excluded from the cache's ok_files set, so the
        files still re-dispatch on the next run (retry semantics preserved)."""
        jsonl_file = tmp_path / "evidence.jsonl"
        raw_client = MagicMock()
        raw_client.chat.completions.create.side_effect = httpx.ReadTimeout("timeout")

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="t", jsonl_file=jsonl_file,
                    source_file_paths=["src/a.py", "src/b.py"],
                ),
                config=api_config,
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        assert {m["file"] for m in markers} == {"src/a.py", "src/b.py"}
        assert all(m["status"] == "error" for m in markers)
        # A failed call produces no findings.
        assert self._findings_only(lines) == []

    def test_truncated_response_emits_error_markers(self, tmp_path, api_config):
        """A length-truncated response is lossy: emit 'error' markers so the
        files re-dispatch and the breaker/reachability guard see the failure,
        while still surfacing the partial findings recovered before the cut."""
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("X-1", "violation", "a.py", 1, "minor", "x"))
        raw_client = _mock_raw_client_finish(content, "length")

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="t", jsonl_file=jsonl_file,
                    source_file_paths=["src/a.py"],
                ),
                config=api_config,
            )

        lines = self._read_jsonl(jsonl_file)
        markers = self._markers(lines)
        assert {m["file"] for m in markers} == {"src/a.py"}
        assert all(m["status"] == "error" for m in markers)
        # Partial findings recovered before the cut are still surfaced.
        assert len(self._findings_only(lines)) == 1

    def test_no_source_files_no_markers(self, tmp_path, api_config):
        """Backward-compat: callers that don't pass source_file_paths get
        finding writes only -- the CLI dim runner is the typical caller and
        that's expected when the whole-dim file list isn't known here."""
        jsonl_file = tmp_path / "evidence.jsonl"
        content = _make_findings_json(("X-1", "violation", "a.py", 1, "minor", "x"))
        raw_client = _mock_raw_client(content)

        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                request=ApiAnalysisRequest(
                    prompt="t", jsonl_file=jsonl_file, source_file_paths=None,
                ),
                config=api_config,
            )

        lines = self._read_jsonl(jsonl_file)
        assert self._markers(lines) == []
        assert len(self._findings_only(lines)) == 1
