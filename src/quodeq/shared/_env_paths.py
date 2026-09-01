"""Environment-based configuration accessors -- filesystem paths."""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.shared._env import _sanitized_env_path

_DEFAULT_EVALUATIONS_DIR = Path.home() / ".quodeq" / "evaluations"


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
        return _sanitized_env_path(from_env)
    if default is not None:
        return default
    return str(_DEFAULT_EVALUATIONS_DIR)


def get_findings_file(env: dict[str, str] | None = None) -> str | None:
    """Return the findings file path from environment, or None."""
    return (env or os.environ).get("FINDINGS_FILE")


def get_quodeq_dir(env: dict[str, str] | None = None) -> Path:
    """Return the base Quodeq state directory.

    Resolution order: QUODEQ_DIR env var, then ~/.quodeq. Recomputes the
    default on each call so test monkeypatches of ``Path.home`` are honored.
    """
    from_env = (env or os.environ).get("QUODEQ_DIR")
    if from_env:
        return Path(_sanitized_env_path(from_env))
    return Path.home() / ".quodeq"


_DEFAULT_CLONES_DIR = Path.home() / ".quodeq" / "clones"


def get_clones_dir(env: dict[str, str] | None = None) -> Path:
    """Return the directory where ephemeral clones live.

    Resolution order: QUODEQ_CLONES_DIR env var, then ~/.quodeq/clones.
    Recomputes the default on each call so test monkeypatches of
    ``Path.home`` are honored.
    """
    from_env = (env or os.environ).get("QUODEQ_CLONES_DIR")
    if from_env:
        return Path(_sanitized_env_path(from_env))
    return Path.home() / ".quodeq" / "clones"


_DEFAULT_GRADE_FORMULA_PATH = Path.home() / ".quodeq" / "grade_formula.json"


def get_grade_formula_path(env: dict[str, str] | None = None) -> str:
    """Return the path of the user-tuned grade-formula params file.

    Resolution order: QUODEQ_GRADE_FORMULA_PATH env var, then
    ~/.quodeq/grade_formula.json. Env override exists so the test suite can
    sandbox the file (a developer's real custom formula must never leak into
    score assertions).
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_GRADE_FORMULA_PATH" in environ:
        return _sanitized_env_path(environ["QUODEQ_GRADE_FORMULA_PATH"])
    return str(_DEFAULT_GRADE_FORMULA_PATH)
