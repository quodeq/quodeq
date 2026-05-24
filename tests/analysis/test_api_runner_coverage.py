"""Extended tests for _api_runner.py: salvage, enrichment, path resolution."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

instructor = pytest.importorskip("instructor", reason="requires quodeq[api] extra")

import httpx

from quodeq.analysis._api_runner import (
    ApiRunnerConfig,
    _LOCAL_TIMEOUT,
    _build_router_context,
    _call_api,
    _Finding,
    _Findings,
    _FindingType,
    _is_timeout_error,
    _resolve_file_paths,
    _salvage_partial_findings,
    _Severity,
    run_api_analysis,
)


# ---------------------------------------------------------------------------
# _salvage_partial_findings
# ---------------------------------------------------------------------------

class TestSalvagePartialFindings:
    def test_extracts_valid_findings_from_malformed_json(self):
        raw = '{"findings": [{"req":"S-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"test","snippet":"x = 1","reason":"bad"}, BROKEN'
        result = _salvage_partial_findings(raw)
        assert len(result) >= 1
        assert result[0]["req"] == "S-1"

    def test_returns_empty_for_completely_invalid(self):
        result = _salvage_partial_findings("totally invalid no json here")
        assert result == []

    def test_skips_invalid_objects(self):
        # First object is well-formed and valid; second lacks required fields and must be dropped.
        raw = (
            '{"req":"X-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"ok","snippet":"x = 1","reason":"r"} '
            '{"not_a_finding": true}'
        )
        result = _salvage_partial_findings(raw)
        assert len(result) == 1
        assert result[0]["req"] == "X-1"

    def test_handles_multiple_valid_objects(self):
        raw = (
            '{"req":"A-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"one","snippet":"x = 1","reason":"r"} '
            '{"req":"B-2","t":"compliance","file":"b.py","line":2,"severity":"major","w":"two","snippet":"y = 2","reason":"r"}'
        )
        result = _salvage_partial_findings(raw)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _is_timeout_error
# ---------------------------------------------------------------------------

class TestIsTimeoutError:
    """Timeout detection must see through Instructor's retry wrapper.

    When Instructor exhausts retries it raises ``InstructorRetryException``
    with the original ``ReadTimeout`` buried in ``failed_attempts``. A bare
    ``isinstance(exc, httpx.ReadTimeout)`` misses these wrapped cases and the
    user sees a generic "no findings recovered" instead of the actionable
    timeout WARN.
    """

    def test_bare_read_timeout(self):
        assert _is_timeout_error(httpx.ReadTimeout("read timeout")) is True

    def test_bare_timeout_exception(self):
        assert _is_timeout_error(httpx.TimeoutException("timeout")) is True

    def test_unrelated_exception(self):
        assert _is_timeout_error(ValueError("not a timeout")) is False

    def test_no_failed_attempts_attribute(self):
        """Plain exceptions without failed_attempts return False cleanly."""
        assert _is_timeout_error(RuntimeError("boom")) is False

    def test_wrapped_read_timeout_in_failed_attempts(self):
        """Instructor's retry wrapper stashes the original exception per attempt."""
        wrapper = RuntimeError("InstructorRetryException")
        # Duck-typed failed_attempts: any object with .exception attribute
        attempt = MagicMock(exception=httpx.ReadTimeout("upstream timed out"))
        wrapper.failed_attempts = [attempt]
        assert _is_timeout_error(wrapper) is True

    def test_failed_attempts_with_non_timeout(self):
        """Validation errors in failed_attempts must not be misread as timeouts."""
        wrapper = RuntimeError("InstructorRetryException")
        attempt = MagicMock(exception=ValueError("schema mismatch"))
        wrapper.failed_attempts = [attempt]
        assert _is_timeout_error(wrapper) is False

    def test_failed_attempts_mixed_one_timeout_wins(self):
        """At least one wrapped timeout means we should categorise the whole call as a timeout."""
        wrapper = RuntimeError("InstructorRetryException")
        wrapper.failed_attempts = [
            MagicMock(exception=ValueError("first attempt bad json")),
            MagicMock(exception=httpx.ReadTimeout("second attempt timed out")),
        ]
        assert _is_timeout_error(wrapper) is True

    def test_empty_failed_attempts(self):
        wrapper = RuntimeError("InstructorRetryException")
        wrapper.failed_attempts = []
        assert _is_timeout_error(wrapper) is False


# ---------------------------------------------------------------------------
# _call_api
# ---------------------------------------------------------------------------

class TestCallApi:
    def test_passes_context_size_as_num_ctx(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
            context_size=8192,
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            _call_api("test", config)

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"]["num_ctx"] == 8192

    def test_no_num_ctx_when_zero(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
            context_size=0,
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            _call_api("test", config)

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "num_ctx" not in kwargs.get("extra_body", {})

    def test_includes_max_tokens_when_set(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
            max_tokens=4096,
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            _call_api("test", config)

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == 4096

    def test_no_max_tokens_when_none(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            _call_api("test", config)

        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "max_tokens" not in kwargs

    def test_uses_ollama_as_default_key(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
            api_key="",
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai") as mock_openai:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            _call_api("test", config)

        mock_openai.OpenAI.assert_called_once_with(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            timeout=_LOCAL_TIMEOUT,
        )

    def test_returns_clean_flag_on_success(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _Findings(findings=[
            _Finding(req="X-1", t=_FindingType.violation, file="a.py", line=1,
                     severity=_Severity.minor, w="x", snippet="code", reason="r"),
        ])

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            findings, salvaged = _call_api("test", config)

        assert len(findings) == 1
        assert salvaged is False

    def test_salvages_on_exception(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
        )
        mock_client = MagicMock()
        # Simulate instructor validation failure with valid JSON in the error message
        error_msg = 'Validation failed: {"req":"X-1","t":"violation","file":"a.py","line":1,"severity":"minor","w":"test","snippet":"x = 1","reason":"bad"}'
        mock_client.chat.completions.create.side_effect = Exception(error_msg)

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            findings, salvaged = _call_api("test", config)

        assert len(findings) >= 1
        assert salvaged is True

    def test_returns_empty_on_unsalvageable_error(self):
        config = ApiRunnerConfig(
            model="llama3.1", api_base="http://localhost:11434/v1",
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            findings, salvaged = _call_api("test", config)

        assert findings == []
        assert salvaged is True


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
        findings = _Findings(findings=[
            _Finding(req="NEW-1", t=_FindingType.violation, file="a.py", line=1, w="new", snippet="x = 1", reason="placeholder"),
        ])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"):
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            run_api_analysis(prompt="test", jsonl_file=jsonl, config=config)

        lines = jsonl.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["req"] == "existing"
        assert json.loads(lines[1])["req"] == "NEW-1"

    def test_router_context_built_when_compiled_dir_provided(self, tmp_path):
        """When a compiled dir is passed, the API runner builds a router
        context for enrichment. Without it, the router falls back to a
        default context (no enrichment) but still writes findings + markers."""
        jsonl = tmp_path / "evidence.jsonl"
        config = ApiRunnerConfig(model="m", api_base="http://localhost/v1")
        findings = _Findings(findings=[
            _Finding(req="X-1", t=_FindingType.violation, file="a.py", line=1, w="test", snippet="x = 1", reason="placeholder"),
        ])

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = findings

        with patch("quodeq.analysis._api_runner.instructor") as mock_inst, \
             patch("quodeq.analysis._api_runner.openai"), \
             patch("quodeq.analysis._api_runner._build_router_context",
                   return_value=None) as mock_ctx:
            mock_inst.from_openai.return_value = mock_client
            mock_inst.Mode.JSON = "json"
            run_api_analysis(
                prompt="test", jsonl_file=jsonl, config=config,
                compiled_dir=tmp_path, dimension="security",
            )
            mock_ctx.assert_called_once()
            args = mock_ctx.call_args.args
            assert args[0] == tmp_path  # compiled_dir
            assert args[1] == "security"  # dimension
