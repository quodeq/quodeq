"""Resolve provider API-credential env exports from ai_providers.json.

The scan subprocess reads a cloud provider's API key from the env var named
by the provider's ``api_key_env`` (see analysis/subprocess). This helper
maps user-entered credentials (Settings -> EvaluationOptions) onto those
env names so the service layer can export them without importing from the
analysis layer.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared.env_resolve import resolve_env

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "config" / "ai_providers.json"


def providers_path(env: Mapping[str, str] | None = None) -> Path:
    """Path of ``ai_providers.json``; ``QUODEQ_AI_PROVIDERS_PATH`` overrides the bundled file."""
    return Path(resolve_env(env).get("QUODEQ_AI_PROVIDERS_PATH", str(_DEFAULT_PATH)))


def provider_env_exports(
    provider_id: str | None,
    api_key: str | None,
    api_base: str | None,
) -> dict[str, str]:
    """Return env vars carrying user-entered credentials for *provider_id*.

    A provider with a ``credential_env`` entry (``{"key": ..., "base": ...}``,
    e.g. ``omlx``) exports both under those fixed names. Otherwise the API
    key is exported under the provider's ``api_key_env``, and a base URL only
    when the provider's configured ``api_base`` is an env template
    (``${VAR}``, e.g. the ``custom`` provider) — fixed endpoints are not
    overridable per-run.
    """
    if not provider_id:
        return {}
    try:
        configs = json.loads(providers_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    cfg = configs.get(provider_id)
    if not isinstance(cfg, dict):
        return {}
    credential_env = cfg.get("credential_env")
    if isinstance(credential_env, dict):
        return _generic_credential_exports(credential_env, api_key, api_base)
    exports: dict[str, str] = {}
    key_env = cfg.get("api_key_env")
    if api_key and isinstance(key_env, str) and key_env:
        exports[key_env] = api_key
    base_template = cfg.get("api_base", "")
    if (
        api_base
        and isinstance(base_template, str)
        and base_template.startswith("${")
        and base_template.endswith("}")
    ):
        exports[base_template[2:-1]] = api_base
    return exports


def _generic_credential_exports(
    credential_env: dict, api_key: str | None, api_base: str | None,
) -> dict[str, str]:
    """Export *api_key*/*api_base* under a provider's fixed ``credential_env``
    names (``key``/``base``), whichever are present."""
    exports: dict[str, str] = {}
    key_name = credential_env.get("key")
    if api_key and isinstance(key_name, str) and key_name:
        exports[key_name] = api_key
    base_name = credential_env.get("base")
    if api_base and isinstance(base_name, str) and base_name:
        exports[base_name] = api_base
    return exports
