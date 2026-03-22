"""File priority scoring — ranks source files by analysis importance."""
from __future__ import annotations

import fnmatch
import json
import os
from functools import lru_cache
from pathlib import Path

from quodeq.config.paths import default_paths


@lru_cache(maxsize=1)
def load_priority_config() -> dict:
    """Load file priority config. Cached after first call."""
    config_path = default_paths().root / "config" / "file_priority.json"
    return json.loads(config_path.read_text())


def compute_base_score(filepath: str, category: str | None = None) -> int:
    """Layer 1: base score from path patterns, entry points, and category."""
    config = load_priority_config()
    score = config["default_path_score"]

    filepath_lower = filepath.lower().replace("\\", "/")
    for prefix, boost in config["path_boost"].items():
        if filepath_lower.startswith(prefix) or f"/{prefix}" in filepath_lower:
            score = boost
            break

    basename = os.path.basename(filepath_lower)
    for pattern in config["entry_points"]:
        if fnmatch.fnmatch(basename, pattern.lower()):
            score += config["entry_point_boost"]
            break

    if category and category in config.get("category_keywords", {}):
        keywords = config["category_keywords"][category]
        for kw in keywords:
            if kw in filepath_lower:
                score += config["category_keyword_boost"]
                break

    return score


def compute_dimension_boost(
    filepath: str,
    dimension: str | list[str],
    file_size: int = 0,
) -> int:
    """Layer 2: dimension-specific keyword boost or file-size boost."""
    config = load_priority_config()
    dims = dimension if isinstance(dimension, list) else [dimension]
    filepath_lower = filepath.lower().replace("\\", "/")

    best = 0
    for dim in dims:
        keywords = config.get("dimension_keywords", {}).get(dim, [])
        if not keywords and dim == "maintainability":
            divisor = config.get("maintainability_size_divisor", 2000)
            score = min(5, int(file_size / divisor))
        else:
            score = 0
            for kw in keywords:
                if kw in filepath_lower:
                    score = config.get("dimension_keyword_boost", 5)
                    break
        best = max(best, score)
    return best
