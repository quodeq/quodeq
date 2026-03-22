"""File priority scoring — ranks source files by analysis importance."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from quodeq.config.paths import default_paths


@lru_cache(maxsize=1)
def load_priority_config() -> dict:
    """Load file priority config. Cached after first call."""
    config_path = default_paths().root / "config" / "file_priority.json"
    return json.loads(config_path.read_text())
