"""Load environment variables from .quodeq.env files."""

from __future__ import annotations

import logging
import os

from quodeq.config._config_paths import ConfigPaths

_logger = logging.getLogger(__name__)


def load_env_file(paths: ConfigPaths, target: dict[str, str] | None = None) -> None:
    """Source all ``export VAR=value`` lines from ``.quodeq.env`` into *target*.

    *target* defaults to ``os.environ``.  Already-set keys are NOT
    overwritten, so explicit env takes precedence over the file.

    Pass an explicit *target* dict in tests to avoid mutating the real
    environment.
    """
    if target is None:
        target = os.environ
    if not paths.env_file.exists():
        return
    try:
        lines = paths.env_file.read_text().splitlines()
    except OSError as exc:
        _logger.warning("Failed to read env file %s: %s", paths.env_file, exc)
        return
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in target:
            target[key] = os.path.expanduser(value)
