"""Persisted settings for the shared results repository.

One JSON file at ~/.quodeq/shared.json (QUODEQ_DIR overrides the directory),
following the update/state.py pattern: dataclass, atomic replace, fail-soft reads.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_FILENAME = "shared.json"


@dataclass
class SharedSettings:
    url: str | None = None


def shared_settings_path(env: dict | None = None) -> Path:
    """Resolve the path to the shared settings file.

    Honors QUODEQ_DIR environment variable if set, otherwise uses ~/.quodeq.
    """
    e = env if env is not None else os.environ
    base = e.get("QUODEQ_DIR")
    root = Path(base) if base else Path.home() / ".quodeq"
    return root / _FILENAME


def read_settings(env: dict | None = None) -> SharedSettings:
    """Read the shared settings file, returning empty settings if missing or corrupt."""
    path = shared_settings_path(env=env)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return SharedSettings()
    if not isinstance(data, dict):
        return SharedSettings()
    known = {f for f in SharedSettings().__dict__}
    return SharedSettings(**{k: v for k, v in data.items() if k in known})


def write_settings(settings: SharedSettings, env: dict | None = None) -> None:
    """Write shared settings atomically to disk, fail-silent on error."""
    path = shared_settings_path(env=env)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(settings)), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # fail-silent: a notice is never worth crashing over
