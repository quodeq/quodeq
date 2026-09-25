"""API runner call options: timeouts, thinking knobs, output caps, truncation."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis._api_call import _LOCAL_TIMEOUT
from quodeq.analysis._api_runner import ApiRunnerConfig, call_api

from ._api_runner_helpers import (
    _make_findings_json,
    _mock_raw_client,
    _mock_raw_client_finish,
)


class TestResolveTimeout:
    """The read budget scales with the subagent count on local providers.

    Local servers serve one request per loaded model, so with N subagents a
    queued request waits up to (N-1) inferences before its own starts. A fixed
    read budget times out queued-but-healthy calls, burning the whole budget
    for zero findings and feeding the failure-streak breaker.
    """

    def test_local_single_agent_keeps_default(self):
        from quodeq.analysis._api_call import _resolve_timeout
        cfg = ApiRunnerConfig(model="m", api_base="http://localhost:11434/v1")
        assert _resolve_timeout(cfg, is_openai=False) == _LOCAL_TIMEOUT

    def test_local_read_budget_scales_with_subagents(self):
        from quodeq.analysis._api_call import _resolve_timeout
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", n_subagents=3,
        )
        t = _resolve_timeout(cfg, is_openai=False)
        assert t.read == _LOCAL_TIMEOUT.read * 3
        assert t.connect == _LOCAL_TIMEOUT.connect
        assert t.write == _LOCAL_TIMEOUT.write
        assert t.pool == _LOCAL_TIMEOUT.pool

    def test_cloud_budget_ignores_subagents(self):
        from quodeq.analysis._api_call import _resolve_timeout, _CLOUD_TIMEOUT
        cfg = ApiRunnerConfig(
            model="m", api_base="https://api.openai.com/v1", n_subagents=3,
        )
        assert _resolve_timeout(cfg, is_openai=True) == _CLOUD_TIMEOUT

    def test_read_timeout_override_wins(self):
        from quodeq.analysis._api_call import _resolve_timeout
        # QUODEQ_API_READ_TIMEOUT arrives resolved, as read_timeout_s.
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", n_subagents=2, read_timeout_s=900,
        )
        assert _resolve_timeout(cfg, is_openai=False).read == 900.0

    def test_exported_env_is_not_read_per_call(self, monkeypatch):
        from quodeq.analysis._api_call import _resolve_timeout
        monkeypatch.setenv("QUODEQ_API_READ_TIMEOUT", "900")
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", n_subagents=2,
        )
        assert _resolve_timeout(cfg, is_openai=False).read == _LOCAL_TIMEOUT.read * 2

    def test_call_api_passes_scaled_timeout_to_client(self):
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:8000/v1",
            api_key="k", n_subagents=2,
        )
        raw_client = _mock_raw_client('{"findings":[]}')
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = raw_client
            call_api("prompt", cfg)
        timeout = mock_oa.call_args.kwargs["timeout"]
        assert timeout.read == _LOCAL_TIMEOUT.read * 2


def _create_kwargs(cfg):
    raw_client = _mock_raw_client('{"findings":[]}')
    with patch("openai.OpenAI") as mock_oa:
        mock_oa.return_value.__enter__.return_value = raw_client
        call_api("prompt", cfg)
    return raw_client.chat.completions.create.call_args.kwargs


class TestExtraBodyThinkingControls:
    """Ollama only honours `reasoning_effort`; `chat_template_kwargs` is a
    llama.cpp/vLLM convention it silently ignores. Both must go out to local
    providers or Gemma-style thinking loops blow the read timeout."""

    def test_local_sends_both_thinking_knobs(self, api_config):
        extra = _create_kwargs(api_config)["extra_body"]
        assert extra["reasoning_effort"] == "none"
        assert extra["chat_template_kwargs"] == {"enable_thinking": False}

    def test_openai_sends_only_reasoning_effort(self):
        cfg = ApiRunnerConfig(
            model="gpt", api_base="https://api.openai.com/v1", api_key="k",
        )
        extra = _create_kwargs(cfg)["extra_body"]
        assert extra["reasoning_effort"] == "none"
        assert "chat_template_kwargs" not in extra


class TestLocalOutputCap:
    """Local calls get a default max_tokens so a runaway generation is bounded
    by output budget, not only by the wall-clock read timeout."""

    def test_local_gets_default_cap(self, api_config):
        kwargs = _create_kwargs(api_config)
        assert kwargs["max_tokens"] == 8192

    def test_override_and_zero_disables(self):
        cfg = ApiRunnerConfig(model="m", api_base="http://localhost:8000/v1", max_tokens_override=4096)
        assert _create_kwargs(cfg)["max_tokens"] == 4096
        cfg = ApiRunnerConfig(model="m", api_base="http://localhost:8000/v1", max_tokens_override=0)
        assert "max_tokens" not in _create_kwargs(cfg)

    def test_explicit_config_wins(self):
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:8000/v1", api_key="k",
            max_tokens=123,
        )
        assert _create_kwargs(cfg)["max_tokens"] == 123

    def test_openai_uncapped_by_default(self):
        cfg = ApiRunnerConfig(
            model="gpt", api_base="https://api.openai.com/v1", api_key="k",
        )
        assert "max_tokens" not in _create_kwargs(cfg)


class TestOllamaCtxNoopWarning:
    """Ollama's /v1 endpoint ignores num_ctx (top-level and nested options),
    so a configured context size silently does nothing there. Users must hear
    about it once instead of debugging truncated context."""

    @pytest.fixture(autouse=True)
    def _reset_warn_cache(self):
        from quodeq.analysis._api_call import _warn_ollama_ctx_noop
        _warn_ollama_ctx_noop.cache_clear()
        yield
        _warn_ollama_ctx_noop.cache_clear()

    def test_warns_once_for_ollama_base(self, caplog):
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:11434/v1", api_key="k",
            context_size=32768,
        )
        with caplog.at_level("WARNING"):
            _create_kwargs(cfg)
            _create_kwargs(cfg)
        hits = [r for r in caplog.records if "OLLAMA_CONTEXT_LENGTH" in r.message]
        assert len(hits) == 1

    def test_silent_for_non_ollama_base(self, caplog):
        cfg = ApiRunnerConfig(
            model="m", api_base="http://localhost:8000/v1", api_key="k",
            context_size=32768,
        )
        with caplog.at_level("WARNING"):
            extra = _create_kwargs(cfg)["extra_body"]
        assert extra["num_ctx"] == 32768
        assert not [r for r in caplog.records if "OLLAMA_CONTEXT_LENGTH" in r.message]

    def test_silent_without_context_size(self, api_config, caplog):
        with caplog.at_level("WARNING"):
            _create_kwargs(api_config)
        assert not [r for r in caplog.records if "OLLAMA_CONTEXT_LENGTH" in r.message]


class TestTruncationDetection:
    """A length-truncated response is incomplete: mark the call lossy so the
    file re-dispatches instead of being cached as a clean analysis."""

    def test_truncated_response_is_lossy(self, api_config):
        content = _make_findings_json(
            ("R1", "violation", "a.py", 5, "minor", "x"),
        )
        client = _mock_raw_client_finish(content, "length")
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            _findings, was_lossy = call_api("prompt", api_config)
        assert was_lossy is True

    def test_complete_response_is_not_lossy(self, api_config):
        content = _make_findings_json(
            ("R1", "violation", "a.py", 5, "minor", "x"),
        )
        client = _mock_raw_client_finish(content, "stop")
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            findings, was_lossy = call_api("prompt", api_config)
        assert was_lossy is False
        assert len(findings) == 1


class _FactoryFakeClient:
    """Fake OpenAI-compatible client for asserting ``call_api`` builds its
    client through ``client_factory`` instead of calling ``openai.OpenAI``
    directly."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _create(self, **kwargs):
        msg = SimpleNamespace(content='{"findings": []}')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)])


class TestClientFactory:
    """``call_api`` builds its OpenAI-compatible client through an injectable
    ``client_factory`` so callers/tests can substitute a fake."""

    def test_call_api_builds_client_through_factory(self, api_config):
        built = []

        def factory(**kwargs):
            built.append(kwargs)
            return _FactoryFakeClient(**kwargs)

        findings, lossy = call_api("prompt", api_config, client_factory=factory)
        assert built and built[0]["max_retries"] == 0
        assert lossy is False
        assert findings == []
