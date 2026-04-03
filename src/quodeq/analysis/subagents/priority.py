"""File priority scoring — ranks source files by analysis importance.

This module is the public entry point.  Implementation is split across:
- priority_config: configuration loading and shared constants
- priority_scoring: individual scoring layers
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.analysis.subagents._git_scoring import compute_git_scores
from quodeq.analysis.subagents.priority_config import (
    ScoringInputs,
    _LANG_ALIASES,
    load_priority_config,
    reset_priority_config_cache,
)
from quodeq.analysis.subagents.priority_scoring import (
    compute_base_score,
    compute_dimension_boost,
    compute_fan_in,
    compute_previous_violations,
)

# Re-export everything that consumers import from this module
__all__ = [
    "_LANG_ALIASES",
    "ScoringInputs",
    "compute_base_score",
    "compute_dimension_boost",
    "compute_fan_in",
    "compute_git_scores",
    "compute_previous_violations",
    "load_priority_config",
    "reset_priority_config_cache",
    "PriorityContext",
    "prioritize_files",
]


@dataclass
class PriorityContext:
    """Optional scoring context for file prioritization."""
    category: str | None = None
    language: str | None = None
    evidence_dir: Path | None = None
    config: Any = None


def prioritize_files(
    files: list[str],
    src: Path,
    dimension: str | list[str],
    *,
    context: PriorityContext | None = None,
) -> list[str]:
    """Score and sort files by analysis priority (highest first)."""
    category = context.category if context else None
    language = context.language if context else None
    evidence_dir = context.evidence_dir if context else None
    config = context.config if context else None
    priority_config = load_priority_config()
    fan_in_divisor = priority_config.get("fan_in_divisor", 3)
    fan_in_max = priority_config.get("fan_in_max", 5)
    max_prev_violations = priority_config.get("previous_violations_max", 5)

    # Batch computations (one pass each)
    fan_in = compute_fan_in(files, src, language or "") if language else {}
    git_scores = compute_git_scores(files, src, config=priority_config)
    prev_violations = compute_previous_violations(config, evidence_dir, dimension) if evidence_dir and config else {}

    inputs = ScoringInputs(
        fan_in=fan_in, fan_in_divisor=fan_in_divisor, fan_in_max=fan_in_max,
        git_scores=git_scores, prev_violations=prev_violations,
        max_prev_violations=max_prev_violations,
    )
    scored = _score_files(files, src, dimension, category, inputs)
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [f for _, f in scored]


def _score_files(
    files: list[str], src: Path, dimension: str | list[str], category: str | None,
    inputs: ScoringInputs,
) -> list[tuple[float, str]]:
    """Compute composite priority scores for each file."""
    scored: list[tuple[float, str]] = []
    for f in files:
        base = compute_base_score(f, category)
        file_size = 0
        try:
            file_size = (src / f).stat().st_size
        except OSError:
            pass
        dim_boost = compute_dimension_boost(f, dimension, file_size=file_size)
        fi_raw = inputs.fan_in.get(f, 0)
        fi_score = min(inputs.fan_in_max, fi_raw / inputs.fan_in_divisor) if fi_raw > 0 else 0
        git_score = inputs.git_scores.get(f, 0)
        pv_count = inputs.prev_violations.get(f, 0)
        pv_score = min(inputs.max_prev_violations, pv_count)
        total = base + dim_boost + fi_score + git_score + pv_score
        scored.append((total, f))
    return scored
