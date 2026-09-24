"""Environment-based configuration for the services layer.

``quodeq.services`` inner modules never read the environment directly;
overrides are resolved here, lazily per call, and passed in (or read once by
a composition point and threaded through). Each resolver mirrors the exact
default/parse rule the service module it replaces used to apply -- see each
docstring for the one-line contract.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared.env import env_float, env_int

RUN_DIM_CACHE_MAX_DEFAULT = 256
MAX_HISTORY_RUNS_DEFAULT = 100
CANCEL_GRACE_S_DEFAULT = 30.0
MAX_CONCURRENT_JOBS_DEFAULT = 8
JOB_TIMEOUT_CAP_S_DEFAULT = 0.0
MAX_VIOLATION_FILES_DEFAULT = 20


def run_dim_cache_max(env: Mapping[str, str] | None = None) -> int:
    """QUODEQ_RUN_DIM_CACHE_MAX, default 256; invalid -> default (0 is a valid size)."""
    src = os.environ if env is None else env
    try:
        return int(src.get("QUODEQ_RUN_DIM_CACHE_MAX", str(RUN_DIM_CACHE_MAX_DEFAULT)))
    except (ValueError, TypeError):
        return RUN_DIM_CACHE_MAX_DEFAULT


def max_history_runs(env: Mapping[str, str] | None = None) -> int:
    """QUODEQ_MAX_HISTORY_RUNS, default 100; 0 or invalid -> default."""
    return env_int("QUODEQ_MAX_HISTORY_RUNS", MAX_HISTORY_RUNS_DEFAULT, minimum=1, env=env)


def cancel_grace_s(env: Mapping[str, str] | None = None) -> float:
    """QUODEQ_CANCEL_GRACE_S, default 30.0 seconds; negative or invalid -> default."""
    return env_float("QUODEQ_CANCEL_GRACE_S", CANCEL_GRACE_S_DEFAULT, minimum=0.0, env=env)


def max_concurrent_jobs(env: Mapping[str, str] | None = None) -> int:
    """QUODEQ_MAX_CONCURRENT_JOBS, default 8; non-positive or invalid -> default."""
    return env_int("QUODEQ_MAX_CONCURRENT_JOBS", MAX_CONCURRENT_JOBS_DEFAULT, minimum=1, env=env)


def job_persist_dir(env: Mapping[str, str] | None = None) -> Path:
    """QUODEQ_JOB_PERSIST_DIR, else ``run/jobs`` next to the index DB.

    Mirrors ``get_score_cache_path``, so the test suite's QUODEQ_INDEX_DB_PATH
    override auto-isolates this store too; that itself defaults to
    ``~/.quodeq``. Hardcoding the home fallback here let pytest runs write
    fake jobs into the developer's real dashboard.
    """
    explicit = (os.environ if env is None else env).get("QUODEQ_JOB_PERSIST_DIR")
    if explicit:
        return Path(explicit)
    from quodeq.shared.env import get_index_db_path  # noqa: PLC0415 -- avoid import-time cost

    # Matches the pre-existing behavior: only the QUODEQ_JOB_PERSIST_DIR read
    # above honors an injected *env*; the index-DB fallback always reads the
    # real process environment (get_index_db_path's own default parameter).
    return Path(get_index_db_path()).parent / "run" / "jobs"


def job_timeout_cap_s(env: Mapping[str, str] | None = None) -> float:
    """QUODEQ_JOB_TIMEOUT_S, default 0.0 (no cap); negative or invalid -> default."""
    return env_float("QUODEQ_JOB_TIMEOUT_S", JOB_TIMEOUT_CAP_S_DEFAULT, minimum=0.0, env=env)


def max_violation_files(env: Mapping[str, str] | None = None) -> int:
    """QUODEQ_MAX_VIOLATION_FILES, default 20; invalid -> default.

    No minimum clamp (matches the pre-existing behavior): 0 or a negative
    value parses through unchanged, only a non-numeric value falls back.
    """
    return env_int("QUODEQ_MAX_VIOLATION_FILES", MAX_VIOLATION_FILES_DEFAULT, env=env)
