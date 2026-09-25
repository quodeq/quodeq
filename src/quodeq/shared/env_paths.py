"""Environment-based configuration accessors -- filesystem paths."""
from __future__ import annotations

from pathlib import Path

from quodeq.shared._env_sanitize import sanitized_env_path
from quodeq.shared.env_resolve import resolve_env

_QUODEQ_HOME_DIRNAME = ".quodeq"  # base state dir under the user's home


def home_state_dir() -> Path:
    """``~/.quodeq``, the default base for Quodeq's state (``QUODEQ_DIR`` is not consulted).

    Read on each call so test monkeypatches of ``Path.home`` are honored.
    """
    return Path.home() / _QUODEQ_HOME_DIRNAME


def get_static_dist(env: dict[str, str] | None = None) -> str | None:
    """Return the static dist path from environment, or the user-level cache."""
    from_env = resolve_env(env).get("QUODEQ_STATIC_DIST")
    if from_env:
        return from_env
    # Check user-level cache (built on demand by `quodeq dashboard`)
    cached = home_state_dir() / "static"
    if cached.is_dir() and (cached / "index.html").exists():
        return str(cached)
    return None


def get_evaluations_dir(default: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the evaluations directory from environment or user-level default.

    Priority: QUODEQ_EVALUATIONS_DIR env var > explicit *default* > ~/.quodeq/evaluations.
    Recomputes the default on each call so test monkeypatches of ``Path.home``
    are honored.
    """
    from_env = resolve_env(env).get("QUODEQ_EVALUATIONS_DIR")
    if from_env:
        return sanitized_env_path(from_env)
    if default is not None:
        return default
    return str(home_state_dir() / "evaluations")


def get_findings_file(env: dict[str, str] | None = None) -> str | None:
    """Return the findings file path from environment, or None."""
    return resolve_env(env).get("FINDINGS_FILE")


def get_quodeq_dir(env: dict[str, str] | None = None) -> Path:
    """Return the base Quodeq state directory.

    Resolution order: QUODEQ_DIR env var, then ~/.quodeq. Recomputes the
    default on each call so test monkeypatches of ``Path.home`` are honored.
    """
    from_env = resolve_env(env).get("QUODEQ_DIR")
    if from_env:
        return Path(sanitized_env_path(from_env))
    return home_state_dir()


def get_clones_dir(env: dict[str, str] | None = None) -> Path:
    """Return the directory where ephemeral clones live.

    Resolution order: QUODEQ_CLONES_DIR env var, then ~/.quodeq/clones.
    Recomputes the default on each call so test monkeypatches of
    ``Path.home`` are honored.
    """
    from_env = resolve_env(env).get("QUODEQ_CLONES_DIR")
    if from_env:
        return Path(sanitized_env_path(from_env))
    return home_state_dir() / "clones"


def get_grade_formula_path(env: dict[str, str] | None = None) -> str:
    """Return the path of the user-tuned grade-formula params file.

    Resolution order: QUODEQ_GRADE_FORMULA_PATH env var, then
    ~/.quodeq/grade_formula.json. Env override exists so the test suite can
    sandbox the file (a developer's real custom formula must never leak into
    score assertions). Recomputes the default on each call so test
    monkeypatches of ``Path.home`` are honored.
    """
    environ = resolve_env(env)
    if "QUODEQ_GRADE_FORMULA_PATH" in environ:
        return sanitized_env_path(environ["QUODEQ_GRADE_FORMULA_PATH"])
    return str(home_state_dir() / "grade_formula.json")


def run_dir_path(env: dict[str, str] | None = None) -> Path:
    """Return the user-private runtime directory, without creating it.

    ``QUODEQ_RUN_DIR`` overrides the default ``~/.quodeq/run``; it must be
    absolute so two processes reading it from different working directories
    agree on the same sockets and pid files. Pure: callers that need the
    directory to exist use :func:`ensure_run_dir`.
    """
    raw = resolve_env(env).get("QUODEQ_RUN_DIR")
    if raw and not Path(raw).is_absolute():
        raise ValueError(f"QUODEQ_RUN_DIR must be an absolute path, got: {raw!r}")
    return Path(raw) if raw else home_state_dir() / "run"


def ensure_run_dir(env: dict[str, str] | None = None) -> Path:
    """Return :func:`run_dir_path`, creating it (and parents) if needed."""
    run_dir = run_dir_path(env)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
