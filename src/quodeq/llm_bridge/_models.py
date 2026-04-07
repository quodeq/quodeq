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


def get_known_models() -> dict[str, list[dict]]:
    """Load known model suggestions per CLI provider."""
    global _KNOWN_MODELS
    if _KNOWN_MODELS is not None:
        return _KNOWN_MODELS
    try:
        _KNOWN_MODELS = json.loads(_models_path().read_text())
        return _KNOWN_MODELS
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("Could not load known_models.json: %s", exc)
        return {}
