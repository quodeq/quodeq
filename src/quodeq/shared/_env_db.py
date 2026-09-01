"""Environment-based configuration accessors -- SQLite DB paths and kill switches."""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.shared._env import _sanitized_env_path

_SQLITE_DISABLE_TRUTHY = {"1", "true", "yes", "on"}

_DEFAULT_INDEX_DB_PATH = Path.home() / ".quodeq" / "index.db"


def get_index_db_path(default: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the absolute path to the SQLite run index DB.

    Resolution order: QUODEQ_INDEX_DB_PATH env var, then *default*, then
    ~/.quodeq/index.db. Always returns a str for downstream Path/sqlite3 use.
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_INDEX_DB_PATH" in environ:
        return _sanitized_env_path(environ["QUODEQ_INDEX_DB_PATH"])
    return default or str(_DEFAULT_INDEX_DB_PATH)


_DEFAULT_SCORE_CACHE_PATH = Path.home() / ".quodeq" / "score_cache.db"


def get_score_cache_path(env: dict[str, str] | None = None) -> str:
    """Return the absolute path to the rescored-score cache DB.

    Resolution: QUODEQ_SCORE_CACHE_PATH env var, else next to the index DB
    (so the test suite's QUODEQ_INDEX_DB_PATH override auto-isolates it), else
    ~/.quodeq/score_cache.db. This cache is disposable -- deleting it is safe.
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_SCORE_CACHE_PATH" in environ:
        return _sanitized_env_path(environ["QUODEQ_SCORE_CACHE_PATH"])
    index_parent = Path(get_index_db_path(env=environ)).parent
    if str(index_parent) not in ("", "."):
        return str(index_parent / "score_cache.db")
    return str(_DEFAULT_SCORE_CACHE_PATH)


def score_cache_disabled(env: dict[str, str] | None = None) -> bool:
    """Return True when QUODEQ_DISABLE_SCORE_CACHE is truthy (operator kill switch)."""
    environ = env if env is not None else os.environ
    return environ.get("QUODEQ_DISABLE_SCORE_CACHE", "").strip().lower() in _SQLITE_DISABLE_TRUTHY


def sqlite_disabled() -> bool:
    """Return True when QUODEQ_DISABLE_SQLITE is set to a truthy value.

    Operator kill switch for the SQLite findings store. When True, the
    analysis pipeline only writes JSONL and read paths only consult JSONL/JSON.
    """
    raw = os.environ.get("QUODEQ_DISABLE_SQLITE", "")
    return raw.strip().lower() in _SQLITE_DISABLE_TRUTHY
