"""Resolve provider API-credential env exports from ai_providers.json.

The scan subprocess reads a cloud provider's API key from the env var named
by the provider's ``api_key_env`` (see analysis/subprocess). This helper
maps user-entered credentials (Settings -> EvaluationOptions) onto those
env names so the service layer can export them without importing from the
analysis layer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "config" / "ai_providers.json"


def _providers_path() -> Path:
    return Path(os.environ.get("QUODEQ_AI_PROVIDERS_PATH", str(_DEFAULT_PATH)))


def provider_env_exports(
    provider_id: str | None,
    api_key: str | None,
    api_base: str | None,
) -> dict[str, str]:
    """Return env vars carrying user-entered credentials for *provider_id*.

    The API key is exported under the provider's ``api_key_env``. A base URL
    is only exported when the provider's configured ``api_base`` is an env
    template (``${VAR}``, e.g. the ``custom`` provider) — fixed endpoints
    are not overridable per-run.
    """
    if not provider_id:
        return {}
    try:
        configs = json.loads(_providers_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    cfg = configs.get(provider_id)
    if not isinstance(cfg, dict):
        return {}
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
