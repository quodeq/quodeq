"""Config and raw LLM call for the API runner: request construction, the
raw ``chat.completions.create`` round-trip, and fatal-vs-transient error
classification. Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, TYPE_CHECKING

import httpx
import openai

from quodeq.analysis._api_response import finish_call, repair_snippetless
from quodeq.analysis._api_schema import SYSTEM_PROMPT
from quodeq.analysis._drop_stats import DropStatsCounter
from quodeq.analysis.errors import (
    REASON_PAYMENT, REASON_QUOTA, FatalProviderError, classify_fatal_provider_message,
)
from quodeq.shared.constants import OLLAMA_DEFAULT_BASE_URL, OLLAMA_DEFAULT_PORT
from quodeq.shared.url_validation import validate_url_safe

if TYPE_CHECKING:
    from quodeq.analysis.run_types import RunConfig

_log = logging.getLogger(__name__)

_OLLAMA_DEFAULT_BASE = f"{OLLAMA_DEFAULT_BASE_URL}/v1"
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

# Distinct base URLs the one-warning-per-base cache below remembers; a run
# configures a handful of providers at most.
_WARN_CACHE_MAX_BASES = 8


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
    # Operator overrides, resolved from the environment by the caller that
    # builds this config (``_api_batch.build_batch_api_config``), never here.
    max_tokens_override: int | None = None
    """QUODEQ_MAX_OUTPUT_TOKENS: replaces the local default cap; 0 disables it."""
    read_timeout_s: int | None = None
    """QUODEQ_API_READ_TIMEOUT: a positive value replaces the read budget outright."""
    repair_enabled: bool = True
    """False (QUODEQ_DISABLE_FINDING_REPAIR) skips the snippet repair re-ask."""
    run_config: "RunConfig | None" = None
    """The run's RunConfig, so ``finish_call`` records drops on its shared
    drop counter. ``None`` (legacy/direct callers) falls back to the
    module-default counter. Filled by ``build_batch_api_config``."""
    drop_counter: "DropStatsCounter | None" = None
    """Checked before ``run_config.drop_counter`` -- lets a caller that leaves
    ``run_config`` unset (the fallback/consolidated builders) still reach it."""


@functools.lru_cache(maxsize=_WARN_CACHE_MAX_BASES)
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
    calls stay uncapped. ``max_tokens_override`` (QUODEQ_MAX_OUTPUT_TOKENS)
    replaces the local default (0 disables the cap).
    """
    if config.max_tokens is not None:
        return config.max_tokens
    if is_openai:
        return None
    override = config.max_tokens_override
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
    ``read_timeout_s`` (QUODEQ_API_READ_TIMEOUT, whole seconds) overrides the
    read budget outright.
    """
    base = _CLOUD_TIMEOUT if is_openai else _LOCAL_TIMEOUT
    override = config.read_timeout_s
    if override is not None and override > 0:
        read = float(override)
    else:
        scale = max(1, config.n_subagents)
        if is_openai or scale == 1:
            return base
        read = base.read * scale
    return httpx.Timeout(
        connect=base.connect, read=read, write=base.write, pool=base.pool,
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
        if exc.status_code == HTTPStatus.PAYMENT_REQUIRED:
            return REASON_PAYMENT, "out of credits (402 payment required)"
        if exc.status_code == HTTPStatus.TOO_MANY_REQUESTS:
            reason = classify_fatal_provider_message(str(exc))
            if reason in (REASON_QUOTA, REASON_PAYMENT):
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
    if ctx_size > 0:
        # Kept for proxies (LiteLLM-style) that forward it to Ollama's native
        # API; direct Ollama ignores it on /v1, hence the warning.
        extra_body["num_ctx"] = ctx_size
        base = config.api_base or _OLLAMA_DEFAULT_BASE
        if f":{OLLAMA_DEFAULT_PORT}" in base:
            _warn_ollama_ctx_noop(base)

    create_kwargs: dict = dict(
        model=config.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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


def _resolve_drop_counter(config: ApiRunnerConfig) -> DropStatsCounter | None:
    """Config's own counter, then run_config's, then None (module default)."""
    if config.drop_counter is not None:
        return config.drop_counter
    return config.run_config.drop_counter if config.run_config is not None else None


def call_api(
    prompt: str,
    config: ApiRunnerConfig,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[list[dict], bool]:
    """Call the LLM raw, validate each finding independently, return ``(findings, was_lossy)``.

    ``was_lossy`` is True when we failed to REACH the model (network/timeout)
    or the response was truncated by the output budget (``finish_reason ==
    "length"``), so findings past the cut are lost. A response where only
    some findings were malformed returns ``(good_findings, False)`` -- the
    call succeeded end-to-end. Dropped malformed findings are logged (count)
    but do not set ``was_lossy``. Findings dropped only for a missing
    ``snippet`` get one repair re-ask (see ``repair_snippetless``) before
    they count as dropped; ``config.repair_enabled`` False
    (QUODEQ_DISABLE_FINDING_REPAIR) turns that off.
    See ``run_api_analysis`` for the marker contract.

    The OpenAI client owns an httpx connection pool whose sockets count
    against the process FD limit; the ``with`` block closes it so a long
    scan (one call per file) doesn't exhaust the FD soft cap.

    *client_factory* builds the OpenAI-compatible client (``openai.OpenAI``
    by default); tests pass a fake.
    """
    if config.api_base and config.api_base != _OLLAMA_DEFAULT_BASE:
        validate_url_safe(config.api_base, allow_private=True)

    create_kwargs, is_openai = _build_create_kwargs(prompt, config)
    timeout = _resolve_timeout(config, is_openai=is_openai)
    _log.debug("Calling %s model=%s (per-finding parse)", config.api_base, config.model)
    start = time.monotonic()
    with (client_factory or openai.OpenAI)(
        base_url=config.api_base,
        api_key=config.api_key or _OLLAMA_DEFAULT_API_KEY,
        timeout=timeout,
        # Disable the SDK's internal timeout retries: each waits the full read
        # budget, compounding one timeout into minutes of dead wall time.
        max_retries=0,
    ) as client:
        try:
            response = client.chat.completions.create(**create_kwargs)
        except (openai.OpenAIError, httpx.HTTPError) as exc:
            _handle_call_exception(exc, config, start)
            return [], True

        choice = response.choices[0] if response.choices else None
        finish_reason = getattr(choice, "finish_reason", None)
        text = (choice.message.content or "") if choice else ""
        # Finishing inside the with block keeps the client open for the
        # snippet repair re-ask finish_call may make through this partial.
        reask = (
            functools.partial(repair_snippetless, client, create_kwargs, config.model)
            if config.repair_enabled else None
        )
        counter = _resolve_drop_counter(config)
        return finish_call(config.model, finish_reason, text, start, reask=reask, counter=counter)
