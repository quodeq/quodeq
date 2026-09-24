"""AI-client and model discovery for the filesystem provider.

Repo browsing lives in ``_browse_mixin.py`` and is inherited from there."""

from __future__ import annotations

import json
import logging
import platform as _platform_module
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from quodeq.analysis.provider_cache import get_provider_configs
from quodeq.config.provider import Provider
from quodeq.services._browse_mixin import FsBrowseMixin
from quodeq.services.wiring import fetch_anthropic_models, fetch_copilot_models, run_cli_models_command
from quodeq.shared.constants import PLATFORM_DARWIN
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.config_loader import get_anthropic_api_url, get_anthropic_api_version
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.utils import get_anthropic_api_key, read_json

_logger = logging.getLogger(__name__)

_CLI_MODEL_TIMEOUT_S = 8
_CLI_OUTPUT_IGNORE_PREFIXES = {"#", "=", "-", "[", "("}
_ANTHROPIC_API_TIMEOUT_S = 8
_DEFAULT_CLIENT_SORT_ORDER = 50  # ai_providers.json's "order" default when unset
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_AI_DEFAULTS_PATH = _PACKAGE_ROOT / "config" / "ai_defaults.json"


def _load_fallback_claude_models() -> list[str]:
    """Load fallback Claude model list from config/ai_defaults.json."""
    try:
        data = read_json(_AI_DEFAULTS_PATH)
        return data.get("fallback_claude_models", [])
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def _fetch_anthropic_models(api_key: str) -> list[str] | None:
    """Fetch model list from the Anthropic API. Returns None on failure."""
    return fetch_anthropic_models(
        api_key,
        url=get_anthropic_api_url(),
        version=get_anthropic_api_version(),
        timeout_s=_ANTHROPIC_API_TIMEOUT_S,
    )


_DEFAULT_CLIENT_IDS = frozenset({Provider.CLAUDE, Provider.CODEX, Provider.GEMINI, Provider.COPILOT})


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
        if cfg.get("type") == "api"
    )
    return _DEFAULT_CLIENT_IDS | api_ids


def _platform_matches(requires: str) -> bool:
    """Return True if the current platform satisfies the requires_platform constraint."""
    if requires == "darwin-arm64":
        is_darwin = sys.platform == PLATFORM_DARWIN
        return is_darwin and _platform_module.machine() == "arm64"
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
        {"id": "gemini", "label": "Gemini"}, {"id": "copilot", "label": "GitHub Copilot"},
    ]

    def __init__(self) -> None:
        self._model_fetchers: dict[str, Callable] = {}
        # Bind the inherited browse half's sink: FsBrowseMixin cannot import a
        # logger of its own (SEP-06), and a silent mkdir failure is unhelpful.
        self._browse_log = SHARED_LOG

    def configure_model_fetchers(self) -> None:
        """Route the clients that have a richer model source than the CLI probe.

        Opt-in rather than done in ``__init__``: a bare mixin (tests, callers
        that register their own fetchers) keeps the plain CLI behaviour.
        """
        self._model_fetchers["claude"] = self._get_claude_models

    def get_ai_clients(self, env: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
        """Return available AI clients (CLI tools that are installed + API providers).

        *env* overrides ``os.environ`` when provided, making the method
        testable without environment mutation.
        """
        environ = resolve_env(env)
        clients: list[dict[str, str]] = []

        # CLI tools: only include if installed
        if "QUODEQ_AI_CLIENTS" in environ:
            ids = [c.strip() for c in environ["QUODEQ_AI_CLIENTS"].split(",") if c.strip()]
            candidates = [{"id": c, "label": c.capitalize()} for c in ids]
        else:
            candidates = self._CLI_CANDIDATES

        for c in candidates:
            clients.append({**c, "type": "cli", "installed": bool(shutil.which(c["id"]))})

        # API providers: always available (no CLI binary needed)
        provider_configs = get_provider_configs()
        # Display labels for provider IDs whose default capitalize() form
        # reads awkwardly (e.g. "Llamacpp" instead of "llama.cpp").
        api_label_overrides = {"llamacpp": "llama.cpp"}
        for provider_id, cfg in provider_configs.items():
            # "custom" is the user-defined endpoint slot; it is configured in
            # Settings, not offered in the client-discovery list.
            if cfg.get("type") == "api" and provider_id != Provider.CUSTOM:
                requires = cfg.get("requires_platform", "")
                if requires and not _platform_matches(requires):
                    continue
                if not any(c["id"] == provider_id for c in clients):
                    clients.append({
                        "id": provider_id,
                        "label": api_label_overrides.get(provider_id, provider_id.capitalize()),
                        "type": "api",
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
        output = run_cli_models_command(client_id, timeout_s=_CLI_MODEL_TIMEOUT_S)
        models = []
        for line in output.splitlines():
            token = line.strip().split()[0] if line.strip() else ""
            if token and token[0] not in _CLI_OUTPUT_IGNORE_PREFIXES:
                models.append(token)
        return {"models": models}

    def get_client_models(self, client_id: str) -> dict[str, Any]:
        """Return available models for a specific AI client."""
        fetcher = self._model_fetchers.get(client_id, self._get_cli_models)
        return fetcher(client_id)

    def _get_claude_models(
        self, _client_id: str = "claude", api_key: str | None = None,
        key_fn: Callable[[], str | None] | None = None,
    ) -> dict[str, list[str]]:
        """Fetch Claude model list from the Anthropic API, with fallback.

        Pass *api_key* to supply a concrete key directly, or *key_fn* to
        override the global ``get_anthropic_api_key()`` accessor (e.g. for
        testing or per-request credential injection).
        """
        key = api_key or (key_fn or get_anthropic_api_key)()
        if key:
            models = _fetch_anthropic_models(key)
            if models:
                return {"models": models}
        return {"models": _load_fallback_claude_models()}
