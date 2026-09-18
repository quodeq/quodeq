"""Fatal provider errors (quota/auth/billing): classification, API call and process result handling."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from quodeq.analysis._api_call import _classify_fatal_api_error
from quodeq.analysis._api_runner import (
    ApiAnalysisRequest,
    ApiRunnerConfig,
    _call_api,
    run_api_analysis,
)
from quodeq.analysis._process import AnalysisError, _check_process_result
from quodeq.analysis.errors import FatalProviderError, classify_fatal_provider_message

pytestmark = pytest.mark.usefixtures("reset_cancellation")


def _openai_error(cls, status: int, message: str):
    response = httpx.Response(status, request=httpx.Request("POST", "http://test/v1"))
    return cls(message, response=response, body=None)


class TestClassifyFatalProviderMessage:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Error: insufficient_quota for this key", "quota"),
            ("You exceeded your current quota, please check your plan", "quota"),
            ("Quota exceeded for quota metric 'requests'", "quota"),
            ("usage limit reached", "quota"),
            ("Credit balance is too low", "payment"),
            ("402 Payment Required", "payment"),
            ("Invalid API key. Please run /login", "auth"),
            ("401 Unauthorized", "auth"),
            ("OAuth token has expired", "auth"),
        ],
    )
    def test_fatal_messages(self, text, expected):
        assert classify_fatal_provider_message(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "connection refused",
            "model not found",
            "rate limit exceeded, retry after 20s",
            "server overloaded, try again",
        ],
    )
    def test_transient_messages(self, text):
        assert classify_fatal_provider_message(text) is None


class TestClassifyFatalApiError:
    def test_authentication_error_is_fatal(self):
        exc = _openai_error(openai.AuthenticationError, 401, "invalid key")
        assert _classify_fatal_api_error(exc)[0] == "auth"

    def test_permission_denied_is_fatal(self):
        exc = _openai_error(openai.PermissionDeniedError, 403, "forbidden")
        assert _classify_fatal_api_error(exc)[0] == "auth"

    def test_402_is_fatal_payment(self):
        exc = _openai_error(openai.APIStatusError, 402, "payment required")
        assert _classify_fatal_api_error(exc)[0] == "payment"

    def test_429_with_quota_body_is_fatal(self):
        exc = _openai_error(
            openai.RateLimitError, 429, "insufficient_quota: check billing"
        )
        assert _classify_fatal_api_error(exc)[0] == "quota"

    def test_bare_429_is_transient(self):
        exc = _openai_error(openai.RateLimitError, 429, "slow down, retry soon")
        assert _classify_fatal_api_error(exc) is None

    def test_connection_error_is_transient(self):
        exc = openai.APIConnectionError(request=httpx.Request("POST", "http://test/v1"))
        assert _classify_fatal_api_error(exc) is None


class TestCallApiFatal:
    def _config(self):
        return ApiRunnerConfig(
            model="test-model", api_base="http://localhost:8000/v1", api_key="k",
        )

    def test_call_api_raises_fatal_on_auth_error(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = _openai_error(
            openai.AuthenticationError, 401, "invalid key"
        )
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            with pytest.raises(FatalProviderError) as exc_info:
                _call_api("prompt", self._config())
        assert exc_info.value.reason == "auth"

    def test_call_api_stays_lossy_on_transient_429(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = _openai_error(
            openai.RateLimitError, 429, "retry shortly"
        )
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            findings, was_lossy = _call_api("prompt", self._config())
        assert findings == []
        assert was_lossy is True

    def test_run_api_analysis_writes_error_markers_then_reraises(self, tmp_path):
        jsonl_file = tmp_path / "evidence.jsonl"
        client = MagicMock()
        client.chat.completions.create.side_effect = _openai_error(
            openai.AuthenticationError, 401, "invalid key"
        )
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            with pytest.raises(FatalProviderError):
                run_api_analysis(
                    request=ApiAnalysisRequest(
                        prompt="p", jsonl_file=jsonl_file,
                        source_file_paths=["a.py", "b.py"],
                    ),
                    config=self._config(),
                )
        text = jsonl_file.read_text()
        assert text.count('"error"') >= 2
        assert "fatal provider error (auth)" in text


class TestCheckProcessResult:
    def _process(self, returncode: int) -> subprocess.Popen:
        process = MagicMock()
        process.returncode = returncode
        return process

    def test_quota_stderr_raises_fatal(self, tmp_path):
        err = tmp_path / "agent.err"
        err.write_text("Credit balance is too low", encoding="utf-8")
        with pytest.raises(FatalProviderError) as exc_info:
            _check_process_result(self._process(1), err)
        assert exc_info.value.reason == "payment"

    def test_usage_limit_stderr_raises_fatal(self, tmp_path):
        err = tmp_path / "agent.err"
        err.write_text("5-hour usage limit reached", encoding="utf-8")
        with pytest.raises(FatalProviderError) as exc_info:
            _check_process_result(self._process(1), err)
        assert exc_info.value.reason == "quota"

    def test_generic_stderr_raises_analysis_error(self, tmp_path):
        err = tmp_path / "agent.err"
        err.write_text("segfault or whatever", encoding="utf-8")
        with pytest.raises(AnalysisError) as exc_info:
            _check_process_result(self._process(1), err)
        assert not isinstance(exc_info.value, FatalProviderError)

    def test_zero_exit_does_not_raise(self, tmp_path):
        _check_process_result(self._process(0), tmp_path / "missing.err")
