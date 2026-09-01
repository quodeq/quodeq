"""Environment-based configuration accessors.

Numeric helpers and the ports/keys/urls accessors stay here; AI-provider,
filesystem-path, sqlite-DB, and embedding accessors live in the four
siblings below and are re-exported so every existing import path
(``from quodeq.shared._env import <name>``, including this project-wide
fan-in's many call sites) keeps working unchanged.
"""
from __future__ import annotations

import logging
import os

from quodeq.shared._config import _get_config


def _sanitized_env_path(raw: str) -> str:
    """Normalize an operator-supplied filesystem path from an env var.

    Env vars are the operator's own trust domain, but expanduser + abspath
    (which collapses '.' and '..' segments) keeps a stray relative or '~'
    value from resolving somewhere surprising at use time, and gives every
    consumer one canonical absolute form.
    """
    return os.path.abspath(os.path.expanduser(raw))


def _env_int(var: str, default: int, env: dict[str, str] | None = None) -> int:
    """Read an environment variable as an int, warn and return *default* on failure."""
    return env_int(var, default, env=env)


def env_int(
    var: str,
    default: int,
    *,
    minimum: int | None = None,
    env: dict[str, str] | None = None,
) -> int:
    """Read an env var as an int; warn and return *default* on parse failure.

    When *minimum* is given, parsed values below it also fall back to *default*.
    """
    raw = (env or os.environ).get(var)
    if raw is not None:
        try:
            value = int(raw)
        except ValueError:
            logging.getLogger(__name__).warning(
                "Invalid %s=%r (expected integer), using default %r", var, raw, default,
            )
        else:
            if minimum is not None and value < minimum:
                logging.getLogger(__name__).warning(
                    "Out-of-range %s=%r (minimum %r), using default %r",
                    var, raw, minimum, default,
                )
            else:
                return value
    return default


def env_float(
    var: str,
    default: float,
    *,
    minimum: float | None = None,
    env: dict[str, str] | None = None,
) -> float:
    """Read an env var as a float; warn and return *default* on parse failure.

    When *minimum* is given, parsed values below it also fall back to *default*.
    """
    raw = (env or os.environ).get(var)
    if raw is not None:
        try:
            value = float(raw)
        except ValueError:
            logging.getLogger(__name__).warning(
                "Invalid %s=%r (expected number), using default %r", var, raw, default,
            )
        else:
            if minimum is not None and value < minimum:
                logging.getLogger(__name__).warning(
                    "Out-of-range %s=%r (minimum %r), using default %r",
                    var, raw, minimum, default,
                )
            else:
                return value
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
from quodeq.shared._env_paths import (  # noqa: F401 — re-export
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
