"""Individual scoring layers for file prioritization."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

from quodeq.analysis.subagents.priority_config import load_priority_config
from quodeq.analysis.subagents.priority_fan_in import compute_fan_in
from quodeq.analysis.subagents.verify import load_previous_findings_for_dimension

# Re-export compute_fan_in so existing imports from this module still work
__all__ = [
    "compute_base_score",
    "compute_dimension_boost",
    "compute_fan_in",
    "compute_previous_violations",
]


def compute_base_score(
    filepath: str, category: str | None = None, config: dict | None = None,
) -> int:
    """Layer 1: base score from path patterns, entry points, and category."""
    config = config or load_priority_config()
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
    config: dict | None = None,
) -> int:
    """Layer 2: dimension-specific keyword boost or file-size boost."""
    config = config or load_priority_config()
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


def compute_previous_violations(
    config: Any, evidence_dir: Path, dimension: str | list[str],
) -> dict[str, int]:
    """Layer 5: count violations per file from previous evaluation.

    Reuses load_previous_findings_for_dimension from verify.py which
    resolves the correct previous run's evidence directory.
    """
    dims = dimension if isinstance(dimension, list) else [dimension]
    counts: dict[str, int] = {}

    for dim in dims:
        try:
            findings = load_previous_findings_for_dimension(config, dim, evidence_dir, quiet=True)
        except (OSError, KeyError, ValueError):
            continue
        for finding in findings:
            if finding.get("t") == "violation" and finding.get("file"):
                f = finding["file"]
                counts[f] = counts.get(f, 0) + 1

    return counts
