"""Known model suggestions for CLI providers."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

_log = logging.getLogger(__name__)


def _models_path() -> Path:
    """Path to known_models.json."""
    return Path(__file__).resolve().parent.parent / "data" / "config" / "known_models.json"


class KnownModelsStore:
    """Lock-guarded lazy cache for known_models.json.

    Instantiable so tests get isolated stores; production shares the
    module-default instance below.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._models: dict | None = None

    def get(self) -> dict[str, list[dict]]:
        if self._models is not None:
            return self._models
        with self._lock:
            if self._models is not None:
                return self._models
            try:
                self._models = json.loads(_models_path().read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _log.warning("Could not load known_models.json: %s", exc)
                return {}
        return self._models

    def reset(self) -> None:
        with self._lock:
            self._models = None


_known_models_store = KnownModelsStore()


def get_known_models(*, _cache: dict | None = None, store: KnownModelsStore | None = None) -> dict[str, list[dict]]:
    """Load known model suggestions per CLI provider.

    *_cache* can be injected for testing to bypass the store entirely and
    return a caller-supplied dict verbatim. *store* selects which cache to
    read/populate, defaulting to the module-wide instance production shares.
    """
    if _cache is not None:
        return _cache
    return (store or _known_models_store).get()


def reset_known_models() -> None:
    """Clear the module-wide cached models. Useful for test isolation."""
    _known_models_store.reset()
