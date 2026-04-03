"""Priority configuration loading and shared constants."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from quodeq.config.paths import default_paths

_LANG_ALIASES = {"typescript": "javascript", "jsx": "javascript", "tsx": "javascript", "kotlin": "java"}


@dataclass(frozen=True)
class ScoringInputs:
    """Grouped scoring parameters to reduce _score_files parameter count."""
    fan_in: dict[str, int]
    fan_in_divisor: int
    fan_in_max: int
    git_scores: dict[str, float]
    prev_violations: dict[str, int]
    max_prev_violations: int


@lru_cache(maxsize=1)
def load_priority_config() -> dict:
    """Load file priority config. Cached after first call."""
    config_path = default_paths().root / "config" / "file_priority.json"
    try:
        return json.loads(config_path.read_text())
    except (FileNotFoundError, PermissionError, json.JSONDecodeError):
        return {}


def reset_priority_config_cache() -> None:
    """Clear the lru_cache on load_priority_config. Useful for test isolation."""
    load_priority_config.cache_clear()
