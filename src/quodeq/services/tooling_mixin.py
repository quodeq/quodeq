"""AI-client and model discovery for the filesystem provider.

Repo browsing lives in ``_browse_mixin.py`` and is inherited from there."""

from __future__ import annotations

import logging
import platform as _platform_module
import shutil
import sys
import threading
import time
from typing import Any, Callable

from quodeq.analysis.provider_cache import get_provider_configs
from quodeq.config.provider import Provider, ProviderType
from quodeq.services._browse_mixin import FsBrowseMixin
from quodeq.services.wiring import (
    CatalogUnavailable, fetch_cli_model_catalog, fetch_copilot_models, run_cli_models_command,
    supports_model_catalog,
)
from quodeq.shared.constants import MACHINE_ARM64, PLATFORM_DARWIN
from quodeq.shared.csv_values import split_csv
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.log_sink import SHARED_LOG

_logger = logging.getLogger(__name__)

_CLI_MODEL_TIMEOUT_S = 8
_CLI_OUTPUT_IGNORE_PREFIXES = {"#", "=", "-", "[", "("}
_CATALOG_TIMEOUT_S = 15
# A catalog changes when the account or the CLI does, not between page loads;
# Settings asks for a refresh explicitly when the user wants one.
_CATALOG_TTL_S = 600
_CATALOG_ERROR_CODE = "CLIENT_MODELS_UNAVAILABLE"
# A refresh this soon after the last lookup is served from the cache, so a
# repeated click (or a scripted loop) cannot spawn a CLI per request.
_CATALOG_REFRESH_MIN_AGE_S = 10
_DEFAULT_CLIENT_SORT_ORDER = 50  # ai_providers.json's "order" default when unset
_REQUIRES_PLATFORM_DARWIN_ARM64 = "darwin-arm64"  # ai_providers.json's "requires_platform" value


_DEFAULT_CLIENT_IDS = frozenset({Provider.CLAUDE, Provider.CODEX, Provider.GEMINI, Provider.AGY, Provider.COPILOT})


def get_allowed_client_ids(env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the set of allowed AI client IDs (lazy, reads env on each call).

    Includes both hardcoded CLI tools and API providers from the provider
    config.  *env* overrides ``os.environ`` when provided, making the
    function testable without environment mutation.
    """
    environ = resolve_env(env)
    if "QUODEQ_AI_CLIENTS" in environ:
        return frozenset(environ["QUODEQ_AI_CLIENTS"].split(","))
    # Include API providers from config alongside default CLI tools
    api_ids = frozenset(
        pid for pid, cfg in get_provider_configs().items()
        if cfg.get("type") == ProviderType.API
    )
    return _DEFAULT_CLIENT_IDS | api_ids


def _platform_matches(requires: str) -> bool:
    """Return True if the current platform satisfies the requires_platform constraint."""
    if requires == _REQUIRES_PLATFORM_DARWIN_ARM64:
        is_darwin = sys.platform == PLATFORM_DARWIN
        return is_darwin and _platform_module.machine() == MACHINE_ARM64
    return True


class FsToolingMixin(FsBrowseMixin):
    """AI-client and model discovery, plus the repo browsing it inherits.

    Held as an attribute by ``FilesystemActionProvider``, not inherited by
    it. Browsing lives in ``FsBrowseMixin`` (``_browse_mixin.py``); the two
    stay one class here so the provider keeps a single tooling collaborator.
    """

    # Default AI CLI candidates. Override via the QUODEQ_AI_CLIENTS env var
    # (comma-separated list of client IDs, e.g. "claude,codex").
    _CLI_CANDIDATES = [
        {"id": "claude", "label": "Claude"}, {"id": "codex", "label": "Codex"},
        {"id": "gemini", "label": "Gemini"}, {"id": "agy", "label": "Antigravity"},
        {"id": "copilot", "label": "GitHub Copilot"},
    ]

    def __init__(self) -> None:
        self._model_fetchers: dict[str, Callable] = {}
        # client id -> (monotonic time stored, payload); successes only.
        self._catalog_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._catalog_lock = threading.Lock()
        # One lookup per client at a time: concurrent requests wait and then
        # read what the first one cached.
        self._catalog_fetch_locks: dict[str, threading.Lock] = {}
        # Bind the inherited browse half's sink: FsBrowseMixin cannot import a
        # logger of its own (SEP-06), and a silent mkdir failure is unhelpful.
        self._browse_log = SHARED_LOG

    def configure_model_fetchers(self) -> None:
        """Route the clients that have a richer model source than the CLI probe.

        Opt-in rather than done in ``__init__``: a bare mixin (tests, callers
        that register their own fetchers) keeps the plain CLI behaviour.
        """
        for client_id in (Provider.CLAUDE, Provider.CODEX):
            if supports_model_catalog(client_id):
                self._model_fetchers[client_id] = self._get_catalog_models

    def get_ai_clients(self, env: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
        """Return available AI clients (CLI tools that are installed + API providers).

        *env* overrides ``os.environ`` when provided, making the method
        testable without environment mutation.
        """
        environ = resolve_env(env)
        clients: list[dict[str, str]] = []

        # CLI tools: only include if installed
        if "QUODEQ_AI_CLIENTS" in environ:
            ids = split_csv(environ["QUODEQ_AI_CLIENTS"])
            candidates = [{"id": c, "label": c.capitalize()} for c in ids]
        else:
            candidates = self._CLI_CANDIDATES

        for c in candidates:
            clients.append({**c, "type": ProviderType.CLI, "installed": bool(shutil.which(c["id"]))})

        # API providers: always available (no CLI binary needed)
        provider_configs = get_provider_configs()
        # Display labels for provider IDs whose default capitalize() form
        # reads awkwardly (e.g. "Llamacpp" instead of "llama.cpp").
        api_label_overrides = {"llamacpp": "llama.cpp"}
        for provider_id, cfg in provider_configs.items():
            # "custom" is the user-defined endpoint slot; it is configured in
            # Settings, not offered in the client-discovery list.
            if cfg.get("type") == ProviderType.API and provider_id != Provider.CUSTOM:
                requires = cfg.get("requires_platform", "")
                if requires and not _platform_matches(requires):
                    continue
                if not any(c["id"] == provider_id for c in clients):
                    clients.append({
                        "id": provider_id,
                        "label": api_label_overrides.get(provider_id, provider_id.capitalize()),
                        "type": ProviderType.API,
                        "installed": True,
                    })

        # Sort by 'order' field from ai_providers.json
        clients.sort(key=lambda c: provider_configs.get(c["id"], {}).get("order", _DEFAULT_CLIENT_SORT_ORDER))

        return {"clients": clients}

    def _get_cli_models(self, client_id: str, env: dict[str, str] | None = None) -> dict[str, Any]:
        if client_id not in get_allowed_client_ids(env=env):
            return {"models": []}
        if not client_id.isalnum():
            return {"models": []}
        if client_id == Provider.COPILOT:
            return fetch_copilot_models(env=env)
        models_args = tuple(get_provider_configs().get(client_id, {}).get("models_args", ("/models",)))
        output = run_cli_models_command(client_id, timeout_s=_CLI_MODEL_TIMEOUT_S, args=models_args)
        models = []
        for line in output.splitlines():
            token = line.strip().split()[0] if line.strip() else ""
            if token and token[0] not in _CLI_OUTPUT_IGNORE_PREFIXES:
                models.append(token)
        return {"models": models}

    def get_client_models(self, client_id: str, *, refresh: bool = False) -> dict[str, Any]:
        """Return available models for a specific AI client.

        *refresh* drops a cached catalog first, so the CLI is asked again.
        """
        if refresh:
            with self._catalog_lock:
                cached = self._catalog_cache.get(client_id)
                if cached and time.monotonic() - cached[0] >= _CATALOG_REFRESH_MIN_AGE_S:
                    del self._catalog_cache[client_id]
        fetcher = self._model_fetchers.get(client_id, self._get_cli_models)
        return fetcher(client_id)

    def _get_catalog_models(self, client_id: str, env: dict[str, str] | None = None) -> dict[str, Any]:
        """The live catalog the CLI reports for its signed-in account, cached.

        ``models`` keeps the plain id list older callers read; ``catalog``
        carries labels, descriptions and the efforts each model supports.
        """
        with self._catalog_lock:
            fetch_lock = self._catalog_fetch_locks.setdefault(client_id, threading.Lock())
        with fetch_lock:
            return self._cached_or_fetched_catalog(client_id, env)

    def _cached_or_fetched_catalog(self, client_id: str, env: dict[str, str] | None) -> dict[str, Any]:
        with self._catalog_lock:
            cached = self._catalog_cache.get(client_id)
        if cached and time.monotonic() - cached[0] < _CATALOG_TTL_S:
            return cached[1]
        try:
            catalog = fetch_cli_model_catalog(
                client_id, env=self._catalog_env(client_id, env), timeout_s=_CATALOG_TIMEOUT_S,
            )
        except CatalogUnavailable as exc:
            _logger.warning("Model list for %s unavailable: %s", client_id, exc)
            return {
                "models": [], "error_code": _CATALOG_ERROR_CODE,
                "error": f"Could not list {client_id} models. Check that it is installed and signed in, then retry.",
            }
        payload = {"models": [entry["id"] for entry in catalog], "catalog": catalog}
        with self._catalog_lock:
            self._catalog_cache[client_id] = (time.monotonic(), payload)
        return payload

    @staticmethod
    def _catalog_env(client_id: str, env: dict[str, str] | None) -> dict[str, str]:
        """The process env minus what the provider config says the CLI must not see."""
        environ = dict(resolve_env(env))
        for key in get_provider_configs().get(client_id, {}).get("env_remove", []):
            environ.pop(key, None)
        return environ
