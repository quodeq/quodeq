"""Fatal provider errors (quota/auth/billing) abort the run instead of respawning agents."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from quodeq.analysis._api_runner import (
    ApiRunnerConfig,
    _call_api,
    _classify_fatal_api_error,
    run_api_analysis,
)
from quodeq.analysis._loops import _interruption_reason, _raise_on_fatal_cancel
from quodeq.analysis._process import AnalysisError, _check_process_result
from quodeq.analysis.cache._failure_streak import CircuitBreakerError
from quodeq.analysis.errors import FatalProviderError, classify_fatal_provider_message
from quodeq.analysis.subagents._pool_models import SubagentResult
from quodeq.analysis.subagents._pool_scaling import (
    check_agent_failure_streak,
    should_respawn,
)
from quodeq.analysis.subagents._pool_worker import WorkerContext, run_single_agent
from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.shared import cancellation


@pytest.fixture(autouse=True)
def _reset_cancellation():
    cancellation.reset()
    yield
    cancellation.reset()


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
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            with pytest.raises(FatalProviderError) as exc_info:
                _call_api("prompt", self._config())
        assert exc_info.value.reason == "auth"

    def test_call_api_stays_lossy_on_transient_429(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = _openai_error(
            openai.RateLimitError, 429, "retry shortly"
        )
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
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
        with patch("quodeq.analysis._api_runner.openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            with pytest.raises(FatalProviderError):
                run_api_analysis(
                    prompt="p", jsonl_file=jsonl_file, config=self._config(),
                    source_file_paths=["a.py", "b.py"],
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


class _FakeQueue:
    def __init__(self, remaining: int):
        self._remaining = remaining

    def remaining(self) -> int:
        return self._remaining


class TestSpawnGate:
    def test_should_respawn_returns_zero_when_cancelled(self, tmp_path):
        cancellation.request_cancel()
        assert should_respawn(_FakeQueue(5), tmp_path / "q.json", 0.0, 0) == 0

    def test_should_respawn_returns_remaining_when_not_cancelled(self, tmp_path):
        assert should_respawn(_FakeQueue(5), tmp_path / "q.json", 0.0, 0) == 5


def _result(success: bool, error: str = "") -> SubagentResult:
    return SubagentResult(
        agent_id="agent-0", jsonl_file=Path("x.jsonl"),
        stream_file=Path("x.stream"), success=success, error=error,
    )


class TestAgentFailureStreak:
    def test_trips_after_default_streak(self):
        check_agent_failure_streak([_result(False, "boom")] * 5)
        assert cancellation.is_cancelled()
        assert cancellation.cancel_reason() == "agent_failure_streak"

    def test_success_resets_streak(self):
        results = [_result(False)] * 4 + [_result(True)] + [_result(False)] * 4
        check_agent_failure_streak(results)
        assert not cancellation.is_cancelled()

    def test_below_threshold_does_not_trip(self):
        check_agent_failure_streak([_result(False)] * 4)
        assert not cancellation.is_cancelled()

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_AGENT_FAILURE_STREAK", "2")
        check_agent_failure_streak([_result(False)])
        assert not cancellation.is_cancelled()
        check_agent_failure_streak([_result(False)] * 2)
        assert cancellation.is_cancelled()

    def test_zero_disables(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_AGENT_FAILURE_STREAK", "0")
        check_agent_failure_streak([_result(False)] * 50)
        assert not cancellation.is_cancelled()


class TestRunSingleAgentFatal:
    def test_fatal_error_cancels_run_and_returns_failure(self, tmp_path):
        wctx = WorkerContext(
            dimension="security", dimension_key="security",
            evidence_dir=tmp_path, queue_path=tmp_path / "q.json",
        )
        with patch(
            "quodeq.analysis.subagents._pool_worker.run_analysis",
            side_effect=FatalProviderError("quota gone", reason="quota"),
        ):
            result = run_single_agent(0, tmp_path, "prompt", AnalysisConfig(), wctx)
        assert result.success is False
        assert "quota gone" in result.error
        assert cancellation.is_cancelled()
        assert (cancellation.cancel_reason() or "").startswith("provider_fatal:quota")


class TestLoopFatalMapping:
    def test_interruption_reason_for_fatal_exc(self):
        assert _interruption_reason(FatalProviderError("x")) == "provider_fatal"

    def test_interruption_reason_from_cancel_reason(self):
        cancellation.request_cancel(reason="provider_fatal:quota: details")
        assert _interruption_reason() == "provider_fatal"

    def test_interruption_reason_streak(self):
        cancellation.request_cancel(reason="agent_failure_streak")
        assert _interruption_reason() == "agent_failure_streak"

    def test_interruption_reason_plain_cancel(self):
        cancellation.request_cancel()
        assert _interruption_reason() == "cancelled_signal"

    def test_raise_on_fatal_cancel_raises_fatal(self, tmp_path):
        cancellation.request_cancel(reason="provider_fatal:quota: credits gone")
        with pytest.raises(FatalProviderError, match="credits gone"):
            _raise_on_fatal_cancel(tmp_path)

    def test_raise_on_fatal_cancel_raises_breaker_for_streak(self, tmp_path):
        cancellation.request_cancel(reason="agent_failure_streak")
        with pytest.raises(CircuitBreakerError):
            _raise_on_fatal_cancel(tmp_path)

    def test_raise_on_fatal_cancel_noop_without_reason(self, tmp_path):
        cancellation.request_cancel()
        _raise_on_fatal_cancel(tmp_path)

    def test_raise_on_fatal_cancel_noop_when_not_cancelled(self, tmp_path):
        _raise_on_fatal_cancel(tmp_path)

    @staticmethod
    def _write_markers(run_dir, *statuses):
        evidence = run_dir / "evidence"
        evidence.mkdir()
        lines = [
            json.dumps({"_marker": "file_done", "file": f"f{i}.py", "status": s})
            for i, s in enumerate(statuses)
        ]
        (evidence / "security_evidence.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8",
        )

    def test_partial_success_keeps_run_alive(self, tmp_path):
        """Quota died halfway: files were analysed, run finalizes as done."""
        self._write_markers(tmp_path, "ok", "ok", "error")
        cancellation.request_cancel(reason="provider_fatal:quota: credits gone")
        _raise_on_fatal_cancel(tmp_path)  # must not raise

    def test_partial_success_keeps_run_alive_for_streak(self, tmp_path):
        self._write_markers(tmp_path, "ok", "error", "error")
        cancellation.request_cancel(reason="agent_failure_streak")
        _raise_on_fatal_cancel(tmp_path)  # must not raise

    def test_error_only_markers_still_fail_the_run(self, tmp_path):
        """Markers exist but nothing succeeded: the run produced no analysis."""
        self._write_markers(tmp_path, "error", "error")
        cancellation.request_cancel(reason="provider_fatal:quota: credits gone")
        with pytest.raises(FatalProviderError):
            _raise_on_fatal_cancel(tmp_path)


class TestLifecycleMapping:
    def test_fatal_provider_error_recognised_by_name(self):
        from quodeq.analysis.run_lifecycle import RunLifecycleContext
        assert RunLifecycleContext._is_named_error(FatalProviderError, "FatalProviderError")
        assert not RunLifecycleContext._is_named_error(ValueError, "FatalProviderError")
