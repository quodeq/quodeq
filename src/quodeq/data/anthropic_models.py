"""Anthropic models-list API adapter — the HTTP boundary for Claude model discovery.

``services/tooling_mixin.py`` resolves the API key, URL, version and
timeout (config/env resolution stays outside the adapter, per the
config-accessor convention) and owns the fallback policy; this module owns
the HTTP call and response parsing.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def fetch_anthropic_models(
    api_key: str, *, url: str, version: str, timeout_s: float,
) -> list[str] | None:
    """Fetch the Claude model id list from the Anthropic API. None on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": version,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read())
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return models if models else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None
