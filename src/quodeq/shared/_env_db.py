"""Environment-based configuration accessors -- SQLite DB paths and kill switches."""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.shared._env_sanitize import sanitized_env_path
from quodeq.shared.env_paths import get_quodeq_dir
from quodeq.shared.env_resolve import resolve_env

SQLITE_DISABLE_TRUTHY = {"1", "true", "yes", "on"}

_INDEX_DB_FILENAME = "index.db"
_SCORE_CACHE_FILENAME = "score_cache.db"


def get_index_db_path(default: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the absolute path to the SQLite run index DB.

    Resolution order: QUODEQ_INDEX_DB_PATH env var, then *default*, then
    ``<state dir>/index.db`` where the state dir is QUODEQ_DIR or ``~/.quodeq``
    (resolved on each call, so a second instance with its own QUODEQ_DIR never
    reads the live app's index). Always returns a str for downstream
    Path/sqlite3 use.
    """
    environ = resolve_env(env)
    if "QUODEQ_INDEX_DB_PATH" in environ:
        return sanitized_env_path(environ["QUODEQ_INDEX_DB_PATH"])
    return default or str(get_quodeq_dir(environ) / _INDEX_DB_FILENAME)


def get_score_cache_path(env: dict[str, str] | None = None) -> str:
    """Return the absolute path to the rescored-score cache DB.

    Resolution: QUODEQ_SCORE_CACHE_PATH env var, else next to the index DB
    (so the test suite's QUODEQ_INDEX_DB_PATH override auto-isolates it), else
    ``<state dir>/score_cache.db``. This cache is disposable -- deleting it is safe.
    """
    environ = resolve_env(env)
    if "QUODEQ_SCORE_CACHE_PATH" in environ:
        return sanitized_env_path(environ["QUODEQ_SCORE_CACHE_PATH"])
    index_parent = Path(get_index_db_path(env=environ)).parent
    if str(index_parent) not in ("", "."):
        return str(index_parent / _SCORE_CACHE_FILENAME)
    return str(get_quodeq_dir(environ) / _SCORE_CACHE_FILENAME)


def score_cache_disabled(env: dict[str, str] | None = None) -> bool:
    """Return True when QUODEQ_DISABLE_SCORE_CACHE is truthy (operator kill switch)."""
    environ = resolve_env(env)
    return environ.get("QUODEQ_DISABLE_SCORE_CACHE", "").strip().lower() in SQLITE_DISABLE_TRUTHY


def sqlite_disabled(env: dict[str, str] | None = None) -> bool:
    """Return True when QUODEQ_DISABLE_SQLITE is set to a truthy value.

    Operator kill switch for the SQLite findings store. When True, the
    analysis pipeline only writes JSONL and read paths only consult JSONL/JSON.
    """
    environ = env if env is not None else os.environ
    raw = environ.get("QUODEQ_DISABLE_SQLITE", "")
    return raw.strip().lower() in SQLITE_DISABLE_TRUTHY
