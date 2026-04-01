"""File priority scoring — ranks source files by analysis importance."""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from quodeq.analysis.subagents._git_scoring import compute_git_scores
from quodeq.analysis.subagents.verify import load_previous_findings_for_dimension
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


def compute_fan_in(
    files: list[str], src: Path, language: str,
    read_file=None,
) -> dict[str, int]:
    """Layer 3: count how many files import each file.

    *read_file* is an injectable ``(Path) -> str | None`` reader; defaults
    to reading from the filesystem.
    """
    config = load_priority_config()
    lang_key = _LANG_ALIASES.get(language.lower(), language.lower())
    patterns = config.get("import_patterns", {}).get(lang_key)
    if not patterns:
        return {}

    def _default_read(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(errors="ignore")
        except OSError:
            return None

    _read = read_file or _default_read

    # Build filename lookup: stem → relative path
    stem_to_file: dict[str, str] = {}
    for f in files:
        stem = Path(f).stem
        stem_to_file.setdefault(stem, f)

    compiled = [re.compile(p) for p in patterns]
    counts: dict[str, int] = {}

    for f in files:
        content = _read(src / f)
        if content is None:
            continue
        for line in content.splitlines():
            target = _match_import_target(line, compiled, stem_to_file, f)
            if target is not None:
                counts[target] = counts.get(target, 0) + 1

    return counts


def _match_import_target(
    line: str, compiled: list[re.Pattern], stem_to_file: dict[str, str], current_file: str,
) -> str | None:
    """Match a single line against import patterns and return the target file, or None."""
    for pattern in compiled:
        m = pattern.search(line)
        if m:
            imported = m.group(1)
            module_name = imported.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
            target = stem_to_file.get(module_name)
            if target is not None and target != current_file:
                return target
            return None
    return None


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
