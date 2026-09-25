"""Environment-based configuration for standards resolution.

``quodeq.config.ConfigPaths`` never reads the environment for its
evaluators directory field; it is resolved here and passed in.
"""
from __future__ import annotations

from pathlib import Path
from quodeq.shared.env_resolve import resolve_env


def evaluators_dir(env: dict[str, str] | None = None) -> Path:
    """Return the global directory for custom evaluator JSON files.

    Honors QUODEQ_EVALUATORS_DIR; unset means ~/.quodeq/evaluators.
    """
    default = Path.home() / ".quodeq" / "evaluators"
    return Path(resolve_env(env).get("QUODEQ_EVALUATORS_DIR", str(default)))
