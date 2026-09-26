"""Environment-based configuration accessors.

Numeric helpers and the ports/keys/urls accessors stay here; AI-provider,
filesystem-path, sqlite-DB, and embedding accessors live in the four
siblings below and are re-exported, so ``from quodeq.shared.env import <name>`` works for every
accessor (this module is a project-wide fan-in with many call sites).

``sanitized_env_path`` lives in the leaf module ``_env_sanitize.py`` (not
defined here) so ``env_paths.py``/``_env_db.py`` can import it without a
cycle back through this module -- see that module's docstring.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TypeVar

from quodeq.shared._config import get_config
from quodeq.shared._env_sanitize import sanitized_env_path  # noqa: F401 — re-export
from quodeq.shared.env_resolve import resolve_env


def _env_int(var: str, default: int, env: dict[str, str] | None = None) -> int:
    """Read an environment variable as an int, warn and return *default* on failure."""
    return env_int(var, default, env=env)


_NumberT = TypeVar("_NumberT", int, float)


def _env_number(
    var: str,
    default: _NumberT,
    kind: Callable[[str], _NumberT],
    minimum: _NumberT | None,
    env: Mapping[str, str] | None,
    warn: bool = True,
) -> _NumberT:
    """Read an env var through *kind*; warn and return *default* on failure.

    When *minimum* is given, parsed values below it also fall back to *default*.
    ``warn=False`` falls back without logging.
    """
    raw = resolve_env(env).get(var)
    if raw is None:
        return default
    try:
        value = kind(raw)
    except ValueError:
        if warn:
            logging.getLogger(__name__).warning(
                "Invalid %s=%r (expected %s), using default %r",
                var, raw, "integer" if kind is int else "number", default,
            )
        return default
    if minimum is not None and value < minimum:
        if warn:
            logging.getLogger(__name__).warning(
                "Out-of-range %s=%r (minimum %r), using default %r",
                var, raw, minimum, default,
            )
        return default
    return value


def env_int(
    var: str,
    default: int,
    *,
    minimum: int | None = None,
    env: Mapping[str, str] | None = None,
    warn: bool = True,
) -> int:
    """Read an env var as an int; warn and return *default* on parse failure.

    When *minimum* is given, parsed values below it also fall back to *default*.
    ``warn=False`` is for values read on every poll, where a bad setting
    would repeat the same warning each tick.
    """
    return _env_number(var, default, int, minimum, env, warn)


def env_float(
    var: str,
    default: float,
    *,
    minimum: float | None = None,
    env: dict[str, str] | None = None,
    warn: bool = True,
) -> float:
    """Read an env var as a float; warn and return *default* on parse failure.

    When *minimum* is given, parsed values below it also fall back to *default*.
    ``warn=False`` is for values read on every poll, where a bad setting
    would repeat the same warning each time.
    """
    return _env_number(var, default, float, minimum, env, warn)


def get_action_api_port(env: dict[str, str] | None = None) -> int:
    """Return the action API port from environment or default."""
    return _env_int("QUODEQ_ACTION_API_PORT", get_config()["action_api_port"], env=env)


def get_action_api_host(env: dict[str, str] | None = None) -> str:
    """Return the action API host from environment or default."""
    return resolve_env(env).get("QUODEQ_ACTION_API_HOST", get_config()["default_host"])


def get_dashboard_port(env: dict[str, str] | None = None) -> int:
    """Return the dashboard preview port from environment or default."""
    return _env_int("QUODEQ_DASHBOARD_PORT", get_config()["dashboard_port"], env=env)


def get_anthropic_api_key(env: dict[str, str] | None = None) -> str | None:
    """Return the Anthropic API key from environment, or None."""
    return resolve_env(env).get("ANTHROPIC_API_KEY") or None


def get_asvs_url(env: dict[str, str] | None = None) -> str:
    """Return the OWASP ASVS JSON URL from environment or default."""
    return resolve_env(env).get("QUODEQ_ASVS_URL", get_config()["asvs_url"])


def get_github_search_url(env: dict[str, str] | None = None) -> str:
    """Return the GitHub repository search URL from environment or default."""
    return resolve_env(env).get("QUODEQ_GITHUB_SEARCH_URL", get_config()["github_search_url"])


def get_github_raw_base_url(env: dict[str, str] | None = None) -> str:
    """Return the GitHub raw content base URL from environment or default."""
    return resolve_env(env).get("QUODEQ_GITHUB_RAW_BASE_URL", get_config()["github_raw_base_url"])


# ---------------------------------------------------------------------------
# Re-exports -- AI provider/CLI selection
# ---------------------------------------------------------------------------
from quodeq.shared._env_ai import (  # noqa: F401 — re-export
    get_ai_cmd,
    get_ai_cmd_path,
    get_ai_model,
    get_ai_provider,
)

# ---------------------------------------------------------------------------
# Re-exports -- filesystem paths
# ---------------------------------------------------------------------------
from quodeq.shared.env_paths import (  # noqa: F401 — re-export
    get_clones_dir,
    get_evaluations_dir,
    get_findings_file,
    get_grade_formula_path,
    get_quodeq_dir,
    get_static_dist,
)

# ---------------------------------------------------------------------------
# Re-exports -- sqlite DB paths and kill switches
# ---------------------------------------------------------------------------
from quodeq.shared._env_db import (  # noqa: F401 — re-export
    get_index_db_path,
    get_score_cache_path,
    score_cache_disabled,
    sqlite_disabled,
)

# ---------------------------------------------------------------------------
# Re-exports -- semantic precedent embeddings
# ---------------------------------------------------------------------------
from quodeq.shared._env_embeddings import (  # noqa: F401 — re-export
    get_embedding_base_url,
    get_embedding_model,
    get_precedent_similarity_threshold,
    semantic_precedents_enabled,
)
