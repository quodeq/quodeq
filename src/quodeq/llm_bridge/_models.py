"""Known model suggestions for CLI providers."""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_KNOWN_MODELS: dict | None = None


def _models_path() -> Path:
    """Path to known_models.json."""
    return Path(__file__).resolve().parent.parent / "data" / "config" / "known_models.json"


def get_known_models(*, _cache: dict | None = None) -> dict[str, list[dict]]:
    """Load known model suggestions per CLI provider.

    *_cache* can be injected for testing to bypass the module-level cache.
    """
    if _cache is not None:
        return _cache
    global _KNOWN_MODELS
    if _KNOWN_MODELS is not None:
        return _KNOWN_MODELS
    try:
        _KNOWN_MODELS = json.loads(_models_path().read_text())
        return _KNOWN_MODELS
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("Could not load known_models.json: %s", exc)
        return {}


def reset_known_models() -> None:
    """Clear the cached models. Useful for test isolation."""
    global _KNOWN_MODELS
    _KNOWN_MODELS = None
