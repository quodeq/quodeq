"""Git-based file scoring -- churn and recency signals for file prioritization."""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

_GIT_LOG_TIMEOUT_S = 10
_GIT_HASH_LENGTH = 40
_DEFAULT_CHURN_DIVISOR = 4
_DEFAULT_CHURN_MAX = 5
_DEFAULT_RECENCY_DAYS = 14
_DEFAULT_RECENCY_MULTIPLIER = 1.5


def _is_date_line(line: str) -> bool:
    """Check if a line looks like a git date: ``YYYY-MM-DD ...``."""
    return len(line) >= 10 and line[4:5] == "-" and line[7:8] == "-" and " " in line


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
            cwd=str(src), capture_output=True, text=True, timeout=_GIT_LOG_TIMEOUT_S,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def compute_git_scores(files: list[str], src: Path, config: dict | None = None) -> dict[str, float]:
    """Layer 4: git churn and recency scoring."""
    cfg = config or {}
    raw = _run_git_log(src, cfg.get("git_lookback_months", 3))
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
        if len(line) == _GIT_HASH_LENGTH and all(c in "0123456789abcdef" for c in line):
            continue
        # Date lines: "YYYY-MM-DD HH:MM:SS +ZZZZ"
        if _is_date_line(line):
            current_date = line[:10]
            continue
        # File path
        if line in file_set:
            churn[line] = churn.get(line, 0) + 1
            if line not in last_date or current_date > last_date[line]:
                last_date[line] = current_date

    divisor = cfg.get("git_churn_divisor", _DEFAULT_CHURN_DIVISOR)
    max_score = cfg.get("git_churn_max", _DEFAULT_CHURN_MAX)
    recency_days = cfg.get("git_recency_days", _DEFAULT_RECENCY_DAYS)
    recency_mult = cfg.get("git_recency_multiplier", _DEFAULT_RECENCY_MULTIPLIER)
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
