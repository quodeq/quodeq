"""Config and raw LLM call for the API runner: request construction, the
raw ``chat.completions.create`` round-trip, and fatal-vs-transient error
classification. Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass

import httpx
import openai

from quodeq.analysis._api_schema import _SYSTEM_PROMPT, _parse_findings
from quodeq.analysis._drop_stats import record as _record_drop_stats
from quodeq.analysis.errors import FatalProviderError, classify_fatal_provider_message
from quodeq.config.analysis_env import (
    api_read_timeout_override,
    context_size_override,
    max_output_tokens_override,
)
from quodeq.shared.url_validation import validate_url_safe

_log = logging.getLogger(__name__)

_OLLAMA_DEFAULT_BASE = "http://localhost:11434/v1"
_OLLAMA_DEFAULT_API_KEY = "ollama"
_OPENAI_API_HOST = "api.openai.com"
_LOCAL_TIMEOUT = httpx.Timeout(connect=10.0, read=500.0, write=30.0, pool=10.0)
# Cloud calls get a finite timeout too: with max_retries=0 a stalled response
# would otherwise block the analysis worker forever. Read budget matches the
# SDK's own 600s default; a timeout lands in the existing lossy-file branch.
_CLOUD_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
# Default output budget for local calls (QUODEQ_MAX_OUTPUT_TOKENS overrides,
# 0 disables). Healthy per-batch responses are well under 4k tokens; the cap
# bounds a runaway generation by output budget instead of only wall clock. A
# capped response arrives with finish_reason=length and takes the existing
# lossy path (error marker, re-dispatch next run), so nothing is silently lost.
_DEFAULT_LOCAL_MAX_TOKENS = 8192


@dataclass(frozen=True)
class ApiRunnerConfig:
    """Configuration for a single API runner invocation."""

    model: str
    api_base: str
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int | None = None
    context_size: int = 0
    n_subagents: int = 1
    """Pool size this call competes with; scales the local read timeout."""


@functools.lru_cache(maxsize=8)
def _warn_ollama_ctx_noop(api_base: str) -> None:
    """One warning per base URL: Ollama's /v1 endpoint ignores num_ctx
    (top-level and nested options alike, verified on 0.33.1), so a configured
    context size never reaches the model there. The server-side setting is
    the only lever."""
    _log.warning(
        "A context size is configured but %s looks like Ollama, whose "
        "OpenAI-compatible endpoint ignores per-request num_ctx. Set "
        "OLLAMA_CONTEXT_LENGTH (or the Ollama app's context-length setting) "
        "instead.",
        api_base,
    )


def _resolve_max_tokens(config: ApiRunnerConfig, *, is_openai: bool) -> int | None:
    """Output budget for one completion call.

    Explicit config wins; otherwise local calls get a default cap and cloud
    calls stay uncapped. QUODEQ_MAX_OUTPUT_TOKENS overrides the local default
    (0 disables the cap).
    """
    if config.max_tokens is not None:
        return config.max_tokens
    if is_openai:
        return None
    override = max_output_tokens_override()
    if override is not None:
        return override or None
    return _DEFAULT_LOCAL_MAX_TOKENS


def _resolve_timeout(config: ApiRunnerConfig, *, is_openai: bool) -> httpx.Timeout:
    """Read budget for one completion call.

    Local servers serve one request per loaded model, so with N subagents a
    queued request can wait up to (N-1) inferences before its own starts:
    a fixed budget times out queued-but-healthy calls, and each timeout burns
    the whole budget for zero findings. Scale the read budget linearly with N.
    Cloud backends parallelize, so their budget stays fixed.
    QUODEQ_API_READ_TIMEOUT (whole seconds) overrides the read budget outright.
    """
    base = _CLOUD_TIMEOUT if is_openai else _LOCAL_TIMEOUT
    override = api_read_timeout_override()
    if override is not None and override > 0:
        return httpx.Timeout(
            connect=base.connect, read=float(override),
            write=base.write, pool=base.pool,
        )
    scale = max(1, config.n_subagents)
    if is_openai or scale == 1:
        return base
    return httpx.Timeout(
        connect=base.connect, read=base.read * scale,
        write=base.write, pool=base.pool,
    )


def _classify_fatal_api_error(exc: Exception) -> tuple[str, str] | None:
    """Return ``(reason_code, detail)`` when no retry can fix *exc*, else None.

    The OpenAI SDK normalizes every OpenAI-compatible provider's errors into
    typed exceptions with a status code, so one classifier covers ollama,
    llamacpp, openrouter, and custom endpoints alike. 429 is fatal only when
    the body says quota/credits (OpenAI ``insufficient_quota``, OpenRouter
    out-of-credits): a bare 429 is a transient rate limit and stays on the
    lossy-retry path.
    """
    if isinstance(exc, openai.AuthenticationError):
        return "auth", "authentication failed (401)"
    if isinstance(exc, openai.PermissionDeniedError):
        return "auth", "permission denied (403)"
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return "payment", "out of credits (402 payment required)"
        if exc.status_code == 429:
            reason = classify_fatal_provider_message(str(exc))
            if reason in ("quota", "payment"):
                return reason, "quota/credits exhausted (429)"
    return None


def _build_create_kwargs(prompt: str, config: ApiRunnerConfig) -> tuple[dict, bool]:
    """Build the ``chat.completions.create`` kwargs; returns ``(kwargs, is_openai)``."""
    is_openai = _OPENAI_API_HOST in (config.api_base or "")
    extra_body: dict = {}
    # Disable reasoning-mode thinking (Gemma 4, Qwen3); without it they burn
    # 1000s of hidden tokens before the JSON and can loop past the read
    # timeout. Ollama only honours `reasoning_effort` (it silently ignores
    # `chat_template_kwargs` and top-level `think` on /v1); llama.cpp/vLLM
    # style servers take `chat_template_kwargs`, so local providers get both.
    extra_body["reasoning_effort"] = "none"
    if not is_openai:
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    ctx_size = config.context_size
    if ctx_size <= 0:
        ctx_size = context_size_override() or 0
    if ctx_size > 0:
        # Kept for proxies (LiteLLM-style) that forward it to Ollama's native
        # API; direct Ollama ignores it on /v1, hence the warning.
        extra_body["num_ctx"] = ctx_size
        base = config.api_base or _OLLAMA_DEFAULT_BASE
        if ":11434" in base:
            _warn_ollama_ctx_noop(base)

    create_kwargs: dict = dict(
        model=config.model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=config.temperature,
    )
    if is_openai:
        # Cloud OpenAI honours JSON-mode; local providers ignore/reject it.
        create_kwargs["response_format"] = {"type": "json_object"}
    if extra_body:
        create_kwargs["extra_body"] = extra_body
    max_tokens = _resolve_max_tokens(config, is_openai=is_openai)
    if max_tokens is not None:
        create_kwargs["max_tokens"] = max_tokens
    return create_kwargs, is_openai


def _log_call_outcome(
    config: ApiRunnerConfig,
    finish_reason: str | None,
    text: str,
    findings: list[dict],
    dropped: int,
    start: float,
) -> tuple[list[dict], bool]:
    """Record drop stats and log the call's outcome; returns ``(findings, was_lossy)``.

    ``was_lossy`` is True when the response was truncated by the output
    budget (``finish_reason == "length"``), so findings past the cut are
    lost. See ``_call_api`` for the full lossy-vs-dropped contract.
    """
    elapsed = time.monotonic() - start
    # Feed the per-run aggregate so the dimension loops can report ONE
    # drop-ratio signal at end of run instead of N scattered per-call lines.
    _record_drop_stats(dropped=dropped, kept=len(findings))

    # A length-truncated response is an incomplete analysis: the model ran out of
    # output budget mid-stream, so findings after the cut are simply gone. Treat
    # it as lossy so run_api_analysis writes an 'error' marker and the file(s)
    # re-dispatch next run, rather than caching a partial result as 'ok'.
    truncated = finish_reason == "length"
    if truncated:
        _log.warning(
            "Model %s response was truncated (finish_reason=length) after %.0fs; "
            "kept %d finding(s) but the analysis is incomplete and will re-dispatch. "
            "Reduce input size or raise the model context window.",
            config.model, elapsed, len(findings),
        )
    if dropped:
        _log.warning(
            "Model %s: dropped %d malformed finding(s) of %d parsed in %.0fs "
            "(kept %d). The call succeeded; malformed findings were discarded.",
            config.model, dropped, dropped + len(findings), elapsed, len(findings),
        )
    _log.debug(
        "Model %s returned %d valid findings in %.0fs (raw bytes: %d)",
        config.model, len(findings), elapsed, len(text),
    )
    return findings, truncated


def _handle_call_exception(exc: Exception, config: ApiRunnerConfig, start: float) -> None:
    """React to an exception from ``chat.completions.create``.

    Raises ``FatalProviderError`` when no retry can succeed (auth, billing,
    quota); otherwise logs the failure and returns, leaving the caller to
    treat the call as lossy.
    """
    elapsed = time.monotonic() - start
    fatal = _classify_fatal_api_error(exc)
    if fatal is not None:
        reason_code, detail = fatal
        _log.error(
            "Model %s: %s -- no retry can succeed, aborting: %s",
            config.model, detail, str(exc)[:300],
        )
        raise FatalProviderError(
            f"{detail}: {str(exc)[:300]}", reason=reason_code,
        ) from exc
    if isinstance(exc, (httpx.TimeoutException, openai.APITimeoutError)):
        _log.warning(
            "Model %s call timed out after %.0fs. Likely causes: "
            "--n-subagents > 1 with OLLAMA_NUM_PARALLEL=1 (requests "
            "queue and the second exceeds the timeout), or context "
            "too large (on Ollama set OLLAMA_CONTEXT_LENGTH; "
            "QUODEQ_CONTEXT_SIZE only reaches non-Ollama providers).",
            config.model, elapsed,
        )
    else:
        _log.warning(
            "Model %s call failed after %.0fs: %s",
            config.model, elapsed, str(exc)[:300],
        )


def _call_api(prompt: str, config: ApiRunnerConfig) -> tuple[list[dict], bool]:
    """Call the LLM raw, validate each finding independently, return ``(findings, was_lossy)``.

    ``was_lossy`` is True when we failed to REACH the model (network/timeout)
    or the response was truncated by the output budget (``finish_reason ==
    "length"``), so findings past the cut are lost. A response where only
    some findings were malformed returns ``(good_findings, False)`` -- the
    call succeeded end-to-end. Dropped malformed findings are logged (count)
    but do not set ``was_lossy``. See ``run_api_analysis`` for the marker
    contract.

    The OpenAI client owns an httpx connection pool whose sockets count
    against the process FD limit; the ``with`` block closes it so a long
    scan (one call per file) doesn't exhaust the FD soft cap.
    """
    if config.api_base and config.api_base != _OLLAMA_DEFAULT_BASE:
        validate_url_safe(config.api_base, allow_private=True)

    create_kwargs, is_openai = _build_create_kwargs(prompt, config)
    timeout = _resolve_timeout(config, is_openai=is_openai)
    _log.debug("Calling %s model=%s (per-finding parse)", config.api_base, config.model)
    start = time.monotonic()
    with openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key or _OLLAMA_DEFAULT_API_KEY,
        timeout=timeout,
        # Disable the SDK's internal timeout retries: each waits the full read
        # budget, compounding one timeout into minutes of dead wall time.
        max_retries=0,
    ) as client:
        try:
            response = client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            _handle_call_exception(exc, config, start)
            return [], True

    choice = response.choices[0] if response.choices else None
    finish_reason = getattr(choice, "finish_reason", None)
    text = (choice.message.content or "") if choice else ""
    findings, dropped = _parse_findings(text)
    return _log_call_outcome(config, finish_reason, text, findings, dropped, start)
