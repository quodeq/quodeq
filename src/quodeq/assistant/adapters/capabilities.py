"""Detect whether a provider/model pair supports native function calling."""
from __future__ import annotations

import logging
import threading
from typing import Callable

import httpx

from quodeq.core.types.provider import Provider
from quodeq.shared.lru import LRUDict

_logger = logging.getLogger(__name__)

_ASSUME_NATIVE = frozenset({Provider.OPENROUTER, Provider.CUSTOM})
# Distinct (ollama base, model) answers kept per process. The orchestrator asks
# on every assistant turn; the answer only changes when the model does.
_PROBE_CACHE_SIZE = 64
_probe_answers: LRUDict[tuple[str, str], bool] = LRUDict(_PROBE_CACHE_SIZE)
_probe_lock = threading.Lock()
_PROBE_TIMEOUT_S = 5.0  # /api/show is a local Ollama call; short but enough for a cold-started daemon


def _default_probe(url: str, json: dict) -> dict:
    resp = httpx.post(url, json=json, timeout=_PROBE_TIMEOUT_S)
    resp.raise_for_status()
    return resp.json()


def supports_native_tools(
    provider_id: str, api_base: str, model: str, *,
    probe: Callable[[str, dict], dict] | None = None,
) -> bool:
    """Report whether the provider/model pair accepts native tool calls."""
    if provider_id in _ASSUME_NATIVE:
        return True
    if provider_id == Provider.OLLAMA:
        base = api_base.rstrip("/")
        base = base[: -len("/v1")] if base.endswith("/v1") else base
        return _ollama_supports_tools(base, model, probe)
    return False  # llamacpp/omlx: prompted-JSON fallback unless proven otherwise


def _ollama_supports_tools(
    base: str, model: str, probe: Callable[[str, dict], dict] | None,
) -> bool:
    """Ask Ollama's ``/api/show``. Only the default probe's successful answers
    are cached: an injected probe is a test seam, and a failure is retried on
    the next turn."""
    cacheable = probe is None
    if cacheable:
        with _probe_lock:
            known = _probe_answers.get((base, model))
        if known is not None:
            return known
    try:
        info = (probe or _default_probe)(f"{base}/api/show", {"model": model})
    except Exception as exc:  # noqa: BLE001 - any probe failure → fallback path
        _logger.info("ollama capability probe failed: %s", exc)
        return False
    answer = "tools" in info.get("capabilities", [])
    if cacheable:
        with _probe_lock:
            _probe_answers.put((base, model), answer)
    return answer
