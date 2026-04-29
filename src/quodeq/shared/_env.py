"""Environment-based configuration accessors."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from quodeq.shared._config import _get_config

_DEFAULT_QUODEQ_ROOT = Path.home() / ".quodeq"
_DEFAULT_EVALUATIONS_DIR = Path.home() / ".quodeq" / "evaluations"


def get_quodeq_root(env: dict[str, str] | None = None) -> Path:
    """Return the root directory for Quodeq state (default: ~/.quodeq).

    Override via the ``QUODEQ_HOME`` environment variable.
    """
    raw = (env or os.environ).get("QUODEQ_HOME")
    return Path(raw) if raw else _DEFAULT_QUODEQ_ROOT


def get_ai_provider(env: dict[str, str] | None = None) -> str:
    """Return the AI provider from environment or default."""
    return (env or os.environ).get("AI_PROVIDER", _get_config()["ai_provider_default"])


def get_ai_cmd(env: dict[str, str] | None = None) -> str:
    """Return the AI CLI command from environment or default.

    Falls back to AI_PROVIDER when AI_CMD is not set, so that
    ``AI_PROVIDER=ollama`` implies ``AI_CMD=ollama`` unless overridden.
    """
    _env = env or os.environ
    if "AI_CMD" in _env:
        return _env["AI_CMD"]
    if "AI_PROVIDER" in _env:
        return _env["AI_PROVIDER"]
    return _get_config()["ai_cmd_default"]


def get_ai_model(env: dict[str, str] | None = None) -> str | None:
    """Return the AI model from environment, or None."""
    return (env or os.environ).get("AI_MODEL") or None


def _env_int(var: str, default: int, env: dict[str, str] | None = None) -> int:
    """Read an environment variable as an int, warn and return *default* on failure."""
    raw = (env or os.environ).get(var)
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            logging.getLogger(__name__).warning(
                "Invalid %s=%r (expected integer), using default", var, raw,
            )
    return default


def get_action_api_port(env: dict[str, str] | None = None) -> int:
    """Return the action API port from environment or default."""
    return _env_int("QUODEQ_ACTION_API_PORT", _get_config()["action_api_port"], env=env)


def get_action_api_host(env: dict[str, str] | None = None) -> str:
    """Return the action API host from environment or default."""
    return (env or os.environ).get("QUODEQ_ACTION_API_HOST", _get_config()["default_host"])


def get_dashboard_port(env: dict[str, str] | None = None) -> int:
    """Return the dashboard preview port from environment or default."""
    return _env_int("QUODEQ_DASHBOARD_PORT", _get_config()["dashboard_port"], env=env)


def get_static_dist(env: dict[str, str] | None = None) -> str | None:
    """Return the static dist path from environment, or the user-level cache."""
    from_env = (env or os.environ).get("QUODEQ_STATIC_DIST")
    if from_env:
        return from_env
    # Check user-level cache (built on demand by `quodeq dashboard`)
    cached = Path.home() / ".quodeq" / "static"
    if cached.is_dir() and (cached / "index.html").exists():
        return str(cached)
    return None


def get_evaluations_dir(default: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the evaluations directory from environment or user-level default.

    Priority: QUODEQ_EVALUATIONS_DIR env var > explicit *default* > ~/.quodeq/evaluations
    """
    from_env = (env or os.environ).get("QUODEQ_EVALUATIONS_DIR")
    if from_env:
        return from_env
    if default is not None:
        return default
    return str(_DEFAULT_EVALUATIONS_DIR)


def get_anthropic_api_key(env: dict[str, str] | None = None) -> str | None:
    """Return the Anthropic API key from environment, or None."""
    return (env or os.environ).get("ANTHROPIC_API_KEY") or None


def get_asvs_url(env: dict[str, str] | None = None) -> str:
    """Return the OWASP ASVS JSON URL from environment or default."""
    return (env or os.environ).get("QUODEQ_ASVS_URL", _get_config()["asvs_url"])


def get_github_search_url(env: dict[str, str] | None = None) -> str:
    """Return the GitHub repository search URL from environment or default."""
    return (env or os.environ).get("QUODEQ_GITHUB_SEARCH_URL", _get_config()["github_search_url"])


def get_github_raw_base_url(env: dict[str, str] | None = None) -> str:
    """Return the GitHub raw content base URL from environment or default."""
    return (env or os.environ).get("QUODEQ_GITHUB_RAW_BASE_URL", _get_config()["github_raw_base_url"])


def get_findings_file(env: dict[str, str] | None = None) -> str | None:
    """Return the findings file path from environment, or None."""
    return (env or os.environ).get("FINDINGS_FILE")


_DEFAULT_INDEX_DB_PATH = Path.home() / ".quodeq" / "index.db"


def get_index_db_path(default: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the absolute path to the SQLite run index DB.

    Resolution order: QUODEQ_INDEX_DB_PATH env var, then *default*, then
    ~/.quodeq/index.db. Always returns a str for downstream Path/sqlite3 use.
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_INDEX_DB_PATH" in environ:
        return environ["QUODEQ_INDEX_DB_PATH"]
    return default or str(_DEFAULT_INDEX_DB_PATH)


_SQLITE_DISABLE_TRUTHY = {"1", "true", "yes", "on"}


def sqlite_disabled() -> bool:
    """Return True when QUODEQ_DISABLE_SQLITE is set to a truthy value.

    Operator kill switch for the SQLite findings store. When True, the
    analysis pipeline only writes JSONL and read paths only consult JSONL/JSON.
    """
    raw = os.environ.get("QUODEQ_DISABLE_SQLITE", "")
    return raw.strip().lower() in _SQLITE_DISABLE_TRUTHY
