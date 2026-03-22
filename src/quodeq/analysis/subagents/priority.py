"""File priority scoring — ranks source files by analysis importance."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
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


def compute_fan_in(
    files: list[str], src: Path, language: str,
) -> dict[str, int]:
    """Layer 3: count how many files import each file."""
    config = load_priority_config()
    lang_key = language.lower()
    _LANG_ALIASES = {"typescript": "javascript", "jsx": "javascript", "tsx": "javascript", "kotlin": "java"}
    lang_key = _LANG_ALIASES.get(lang_key, lang_key)
    patterns = config.get("import_patterns", {}).get(lang_key)
    if not patterns:
        return {}

    # Build filename lookup: stem → relative path
    stem_to_file: dict[str, str] = {}
    for f in files:
        stem = Path(f).stem
        stem_to_file.setdefault(stem, f)

    compiled = [re.compile(p) for p in patterns]
    counts: dict[str, int] = {}

    for f in files:
        full_path = src / f
        if not full_path.exists():
            continue
        try:
            content = full_path.read_text(errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            for pattern in compiled:
                m = pattern.search(line)
                if m:
                    imported = m.group(1)
                    module_name = imported.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
                    if module_name in stem_to_file:
                        target = stem_to_file[module_name]
                        if target != f:
                            counts[target] = counts.get(target, 0) + 1
                    break

    return counts


def _run_git_log(src: Path, months: int = 3) -> str | None:
    """Run git log and return raw output, or None if git unavailable."""
    if not (src / ".git").exists():
        # Check parent directories too (we might be in a subdirectory)
        check = src
        while check != check.parent:
            if (check / ".git").exists():
                break
            check = check.parent
        else:
            return None
    try:
        result = subprocess.run(
            ["git", "log", f"--since={months} months ago", "--name-only", "--format=%H%n%ai"],
            cwd=str(src), capture_output=True, text=True, timeout=10,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def compute_git_scores(files: list[str], src: Path) -> dict[str, float]:
    """Layer 4: git churn and recency scoring."""
    config = load_priority_config()
    raw = _run_git_log(src, config.get("git_lookback_months", 3))
    if not raw:
        return {}

    file_set = set(files)
    churn: dict[str, int] = {}
    last_date: dict[str, str] = {}

    current_date = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # 40-char hex = commit hash, skip
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            continue
        # Date lines: "YYYY-MM-DD HH:MM:SS +ZZZZ"
        if len(line) >= 10 and line[4:5] == "-" and line[7:8] == "-" and " " in line:
            current_date = line[:10]
            continue
        # File path
        if line in file_set:
            churn[line] = churn.get(line, 0) + 1
            if line not in last_date or current_date > last_date[line]:
                last_date[line] = current_date

    divisor = config.get("git_churn_divisor", 4)
    max_score = config.get("git_churn_max", 5)
    recency_days = config.get("git_recency_days", 14)
    recency_mult = config.get("git_recency_multiplier", 1.5)
    cutoff = (datetime.now() - timedelta(days=recency_days)).strftime("%Y-%m-%d")

    scores: dict[str, float] = {}
    for f in files:
        c = churn.get(f, 0)
        if c == 0:
            continue
        score = min(max_score, c / divisor)
        if last_date.get(f, "") >= cutoff:
            score = min(max_score, score * recency_mult)
        scores[f] = score

    return scores
