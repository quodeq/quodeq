"""Environment-based configuration for standards resolution.

``quodeq.config.ConfigPaths`` never reads the environment for its
evaluators directory field; it is resolved here and passed in.
"""
from __future__ import annotations

import os
from pathlib import Path


def evaluators_dir(env: dict[str, str] | None = None) -> Path:
    """Return the global directory for custom evaluator JSON files.

    Honors QUODEQ_EVALUATORS_DIR; unset means ~/.quodeq/evaluators.
    """
    default = Path.home() / ".quodeq" / "evaluators"
    return Path((env or os.environ).get("QUODEQ_EVALUATORS_DIR", str(default)))
