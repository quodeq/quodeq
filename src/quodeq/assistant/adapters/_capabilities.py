"""Detect whether a provider/model pair supports native function calling."""
from __future__ import annotations

import logging
from typing import Callable

import httpx

_logger = logging.getLogger(__name__)

_ASSUME_NATIVE = frozenset({"openrouter", "custom"})


def _default_probe(url: str, json: dict) -> dict:
    resp = httpx.post(url, json=json, timeout=5.0)
    resp.raise_for_status()
    return resp.json()


def supports_native_tools(
    provider_id: str, api_base: str, model: str, *,
    probe: Callable[[str, dict], dict] | None = None,
) -> bool:
    if provider_id in _ASSUME_NATIVE:
        return True
    if provider_id == "ollama":
        base = api_base.rstrip("/")
        base = base[: -len("/v1")] if base.endswith("/v1") else base
        try:
            info = (probe or _default_probe)(f"{base}/api/show", {"model": model})
        except Exception as exc:  # noqa: BLE001 - any probe failure → fallback path
            _logger.info("ollama capability probe failed: %s", exc)
            return False
        return "tools" in info.get("capabilities", [])
    return False  # llamacpp/omlx: prompted-JSON fallback unless proven otherwise
