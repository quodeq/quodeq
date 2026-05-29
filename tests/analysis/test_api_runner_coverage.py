"""Extended tests for _api_runner.py: salvage, enrichment, path resolution."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

import httpx
import openai

from quodeq.analysis._api_runner import (
    ApiRunnerConfig,
    _LOCAL_TIMEOUT,
    _build_router_context,
    _call_api,
    _Finding,
    _FindingType,
    _parse_findings,
    _resolve_file_paths,
    _Severity,
    run_api_analysis,
)


# ---------------------------------------------------------------------------
# _salvage_partial_findings
# ---------------------------------------------------------------------------

class TestSalvagePartialFindings:
    def test_extracts_valid_findings_from_malformed_json(self):
        raw = '{"findings": [{"req":"S-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"test","snippet":"x = 1","reason":"bad"}, BROKEN'
        result, _ = _parse_findings(raw)
        assert len(result) >= 1
        assert result[0]["req"] == "S-1"

    def test_returns_empty_for_completely_invalid(self):
        result, _ = _parse_findings("totally invalid no json here")
        assert result == []

    def test_skips_invalid_objects(self):
        # First object is well-formed and valid; second lacks required fields and must be dropped.
        raw = (
            '{"req":"X-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"ok","snippet":"x = 1","reason":"r"} '
            '{"not_a_finding": true}'
        )
        result, _ = _parse_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "X-1"

    def test_handles_multiple_valid_objects(self):
        raw = (
            '{"req":"A-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"one","snippet":"x = 1","reason":"r"} '
            '{"req":"B-2","t":"compliance","file":"b.py","line":2,"severity":"major","w":"two","snippet":"y = 2","reason":"r"}'
        )
        result, _ = _parse_findings(raw)
        assert len(result) == 2

    def test_handles_finding_with_nested_req_refs(self):
        """The shallow-regex predecessor silently dropped any finding with a
        nested object; this was the exact failure pattern reported in a real
        run where the model emitted ``req_refs: [{"label": "CWE-..."}]``."""
        raw = (
            '{"req":"R-MAT-5","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"nested","snippet":"x = 1","reason":"r",'
            '"req_refs":[{"label":"CWE-79","url":"https://example.com"}]}'
        )
        result, _ = _parse_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "R-MAT-5"

    def test_handles_bare_findings_concatenated(self):
        """Reproduces the production failure where the model emitted two
        bare finding objects back-to-back (no array wrapper, no separator).
        The JSON parser stops at "trailing characters" after the first."""
        raw = (
            '{"req":"R-MAT-5","t":"violation","file":"a.py","line":10,'
            '"severity":"minor","w":"first","snippet":"foo","reason":"one"}\n'
            '{"req":"R-FT-1","t":"violation","file":"b.py","line":11,'
            '"severity":"minor","w":"second","snippet":"bar","reason":"two"}'
        )
        result, _ = _parse_findings(raw)
        assert len(result) == 2
        assert {r["req"] for r in result} == {"R-MAT-5", "R-FT-1"}

    def test_handles_wrapped_findings_array(self):
        """If the model returned the canonical {"findings":[...]} but
        parsing still needed to walk the structure, the parser should
        recover everything."""
        raw = (
            '{"findings":['
            '{"req":"A-1","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"one","snippet":"x","reason":"r"},'
            '{"req":"B-2","t":"compliance","file":"b.py","line":2,'
            '"severity":"minor","w":"two","snippet":"y","reason":"r"}'
            ']}'
        )
        result, _ = _parse_findings(raw)
        assert len(result) == 2

    def test_handles_findings_buried_in_error_preamble(self):
        """The parser must skip non-JSON preamble text and find the JSON
        object that follows."""
        raw = (
            "1 validation error for _Findings\n"
            "Invalid JSON: trailing characters at line 10 column 4\n"
            "input_value='"
            '{"req":"R-MAT-5","t":"violation","file":"a.py","line":3,'
            '"severity":"minor","w":"ok","snippet":"x","reason":"r"}'
            "', input_type=str"
        )
        result, _ = _parse_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "R-MAT-5"

    def test_parse_findings_returns_findings_and_drop_count(self):
        raw = (
            '{"findings":['
            '{"req":"A-1","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"good","snippet":"x","reason":"valid"},'
            '{"req":"B-2","t":"violation","file":"b.py","line":2,'
            '"severity":"minor","w":"bad","snippet":"y"}'  # missing reason
            ']}'
        )
        findings, dropped = _parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["req"] == "A-1"
        assert dropped == 1

    def test_parse_findings_zero_drops_on_clean_input(self):
        raw = (
            '{"findings":[{"req":"A-1","t":"violation","file":"a.py","line":1,'
            '"severity":"minor","w":"w","snippet":"x","reason":"r"}]}'
        )
        findings, dropped = _parse_findings(raw)
        assert len(findings) == 1
        assert dropped == 0

    def test_parse_findings_container_not_counted_as_drop(self):
        findings, dropped = _parse_findings('{"findings":[]}')
        assert findings == []
        assert dropped == 0

    def test_parse_findings_invalid_finding_counted_once_not_recursed(self):
        # A req-bearing dict that fails validation and has a nested req-bearing
        # object must count as exactly ONE drop (we stop, don't recurse in).
        raw = '{"req":"A-1","t":"violation","extras":{"req":"B-2","t":"violation"}}'
        findings, dropped = _parse_findings(raw)
        assert findings == []
        assert dropped == 1

    def test_parse_findings_recovers_finding_nested_in_container(self):
        # A container without `req` is recursed, so a valid finding nested
        # inside it is still recovered.
        raw = (
            '{"wrapper":{"findings":[{"req":"A-1","t":"violation","file":"a.py",'
            '"line":1,"severity":"minor","w":"w","snippet":"x","reason":"r"}]}}'
        )
        findings, dropped = _parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["req"] == "A-1"
        assert dropped == 0


# ---------------------------------------------------------------------------
# _call_api
# ---------------------------------------------------------------------------

def _mock_response(content: str) -> MagicMock:
    msg = MagicMock(content=content)
    choice = MagicMock(message=msg)
    return MagicMock(choices=[choice])


def _local_config() -> ApiRunnerConfig:
    return ApiRunnerConfig(model="test-model", api_base="http://localhost:11434/v1", api_key="ollama")


def _cloud_config() -> ApiRunnerConfig:
    return ApiRunnerConfig(model="gpt-x", api_base="https://api.openai.com/v1", api_key="sk-x")


_GOOD = (
    '{"req":"A-1","t":"violation","file":"a.py","line":1,'
    '"severity":"minor","w":"one","snippet":"x = 1","reason":"r"}'
)
_GOOD2 = (
    '{"req":"B-2","t":"compliance","file":"b.py","line":2,'
    '"severity":"minor","w":"two","snippet":"y = 2","reason":"r"}'
)
_BAD_MISSING_REASON = (
    '{"req":"C-3","t":"violation","file":"c.py","line":3,'
    '"severity":"minor","w":"bad","snippet":"z"}'
)


class TestCallApi:
    def _run(self, content=None, side_effect=None, config=None):
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            client = MagicMock()
            if side_effect is not None:
                client.chat.completions.create.side_effect = side_effect
            else:
                client.chat.completions.create.return_value = _mock_response(content)
            mock_oa.return_value.__enter__.return_value = client
            findings, lossy = _call_api("prompt", config or _local_config())
            return findings, lossy, mock_oa, client

    def test_clean_wrapped_array(self):
        findings, lossy, *_ = self._run(f'{{"findings":[{_GOOD},{_GOOD2}]}}')
        assert len(findings) == 2
        assert lossy is False

    def test_one_bad_finding_drops_only_itself(self):
        findings, lossy, *_ = self._run(f'{{"findings":[{_GOOD},{_BAD_MISSING_REASON}]}}')
        assert len(findings) == 1
        assert findings[0]["req"] == "A-1"
        assert lossy is False

    def test_bare_concatenated_findings(self):
        findings, lossy, *_ = self._run(f'{_GOOD}\n{_GOOD2}')
        assert {f["req"] for f in findings} == {"A-1", "B-2"}
        assert lossy is False

    def test_garbled_response_not_lossy(self):
        findings, lossy, *_ = self._run("I cannot evaluate this code.")
        assert findings == []
        assert lossy is False

    def test_network_error_is_lossy(self):
        findings, lossy, *_ = self._run(side_effect=httpx.ReadTimeout("upstream"))
        assert findings == []
        assert lossy is True

    def test_cloud_sets_json_object_response_format(self):
        _, _, _, client = self._run(f'{{"findings":[{_GOOD}]}}', config=_cloud_config())
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_local_omits_json_object_response_format(self):
        _, _, _, client = self._run(f'{{"findings":[{_GOOD}]}}', config=_local_config())
        kwargs = client.chat.completions.create.call_args.kwargs
        assert "response_format" not in kwargs

    def test_dropped_findings_logged_with_count(self, caplog):
        # The quodeq logger has propagate=False, so caplog (which adds a handler
        # to the root logger) won't see its records. Re-enable propagation
        # temporarily so pytest's caplog handler receives the messages.
        quodeq_logger = logging.getLogger("quodeq")
        orig_propagate = quodeq_logger.propagate
        quodeq_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="quodeq.analysis._api_runner"):
                findings, lossy, *_ = self._run(
                    f'{{"findings":[{_GOOD},{_BAD_MISSING_REASON},{_BAD_MISSING_REASON}]}}'
                )
        finally:
            quodeq_logger.propagate = orig_propagate
        assert len(findings) == 1
        assert lossy is False
        assert any("dropped 2" in r.message for r in caplog.records)

    def test_connection_error_is_lossy_with_generic_message(self, caplog):
        import openai as _openai
        exc = _openai.APIConnectionError(request=httpx.Request("POST", "http://localhost:11434/v1"))
        with caplog.at_level(logging.WARNING, logger="quodeq.analysis._api_runner"):
            # quodeq logger has propagate=False; flip it so caplog sees the record.
            qlog = logging.getLogger("quodeq")
            orig = qlog.propagate
            qlog.propagate = True
            try:
                findings, lossy, *_ = self._run(side_effect=exc)
            finally:
                qlog.propagate = orig
        assert findings == []
        assert lossy is True
        msgs = " ".join(r.message for r in caplog.records)
        assert "timed out" not in msgs
        assert "call failed" in msgs


# ---------------------------------------------------------------------------
# _resolve_file_paths
# ---------------------------------------------------------------------------

class TestResolveFilePaths:
    def test_resolves_short_name_to_full_path(self):
        findings = [{"file": "app.py", "req": "X-1"}]
        source_paths = ["src/myproject/app.py", "src/myproject/utils.py"]
        result = _resolve_file_paths(findings, source_paths)
        assert result[0]["file"] == "src/myproject/app.py"

    def test_leaves_full_paths_unchanged(self):
        findings = [{"file": "src/myproject/app.py", "req": "X-1"}]
        source_paths = ["src/myproject/app.py"]
        result = _resolve_file_paths(findings, source_paths)
        assert result[0]["file"] == "src/myproject/app.py"

    def test_leaves_unknown_names_unchanged(self):
        findings = [{"file": "unknown.py", "req": "X-1"}]
        source_paths = ["src/myproject/app.py"]
        result = _resolve_file_paths(findings, source_paths)
        assert result[0]["file"] == "unknown.py"

    def test_handles_empty_file_field(self):
        findings = [{"file": "", "req": "X-1"}]
        result = _resolve_file_paths(findings, ["src/app.py"])
        assert result[0]["file"] == ""

    def test_handles_missing_file_field(self):
        findings = [{"req": "X-1"}]
        result = _resolve_file_paths(findings, ["src/app.py"])
        assert "file" not in result[0] or result[0].get("file", "") == ""


# ---------------------------------------------------------------------------
# _build_router_context
# ---------------------------------------------------------------------------

class TestBuildRouterContext:
    def test_returns_none_without_compiled_dir(self):
        """Without a compiled standards dir there is no enrichment context to
        build. Callers fall back to a default-context router (still emits
        markers and writes findings, just no req-ref enrichment)."""
        assert _build_router_context(None, None, None, None) is None

    def test_returns_none_on_load_failure(self):
        """A broken compiled dir must not propagate -- the API runner needs
        to keep writing findings + markers even when enrichment fails."""
        with patch("quodeq.analysis._api_runner.load_compiled_refs",
                   side_effect=OSError("boom")):
            ctx = _build_router_context(Path("/nonexistent"), "security", None, None)
        assert ctx is None


# ---------------------------------------------------------------------------
# run_api_analysis — appends to file
# ---------------------------------------------------------------------------

class TestRunApiAnalysisAppend:
    def test_appends_to_existing_file(self, tmp_path):
        jsonl = tmp_path / "evidence.jsonl"
        jsonl.write_text('{"req":"existing","t":"violation"}\n')

        config = ApiRunnerConfig(model="m", api_base="http://localhost/v1")
        content = json.dumps({"findings": [
            {"req": "NEW-1", "t": "violation", "file": "a.py", "line": 1,
             "w": "new", "snippet": "x = 1", "reason": "placeholder", "severity": "minor"},
        ]})
        raw_client = MagicMock()
        msg = MagicMock(content=content)
        raw_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg)])

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(prompt="test", jsonl_file=jsonl, config=config)

        lines = [ln for ln in jsonl.read_text().strip().split("\n") if ln]
        finding_lines = [json.loads(ln) for ln in lines if "_marker" not in ln]
        assert len(finding_lines) == 2
        assert finding_lines[0]["req"] == "existing"
        assert finding_lines[1]["req"] == "NEW-1"

    def test_router_context_built_when_compiled_dir_provided(self, tmp_path):
        """When a compiled dir is passed, the API runner builds a router
        context for enrichment. Without it, the router falls back to a
        default context (no enrichment) but still writes findings + markers."""
        jsonl = tmp_path / "evidence.jsonl"
        config = ApiRunnerConfig(model="m", api_base="http://localhost/v1")
        content = json.dumps({"findings": [
            {"req": "X-1", "t": "violation", "file": "a.py", "line": 1,
             "w": "test", "snippet": "x = 1", "reason": "placeholder", "severity": "minor"},
        ]})
        raw_client = MagicMock()
        msg = MagicMock(content=content)
        raw_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg)])

        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa, \
             patch("quodeq.analysis._api_runner._build_router_context",
                   return_value=None) as mock_ctx:
            mock_oa.return_value.__enter__.return_value = raw_client
            run_api_analysis(
                prompt="test", jsonl_file=jsonl, config=config,
                compiled_dir=tmp_path, dimension="security",
            )
            mock_ctx.assert_called_once()
            args = mock_ctx.call_args.args
            assert args[0] == tmp_path  # compiled_dir
            assert args[1] == "security"  # dimension
