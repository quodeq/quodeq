"""Git-based file scoring -- churn and recency signals for file prioritization."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from pathlib import Path

from quodeq.data.git_cli import stream_log_names

_GIT_LOG_TIMEOUT_S = 10
_GIT_HASH_LENGTH = 40
_DEFAULT_CHURN_DIVISOR = 4
_DEFAULT_CHURN_MAX = 5
_DEFAULT_RECENCY_DAYS = 14
_DEFAULT_RECENCY_MULTIPLIER = 1.5


def _is_date_line(line: str) -> bool:
    """Check if a line looks like a git date: ``YYYY-MM-DD ...``."""
    return len(line) >= 10 and line[4:5] == "-" and line[7:8] == "-" and " " in line


def _has_git(src: Path) -> bool:
    """Check if *src* (or a parent) is inside a git repository."""
    if (src / ".git").exists():
        return True
    check = src
    while check != check.parent:
        if (check / ".git").exists():
            return True
        check = check.parent
    return False


def _iter_git_log(src: Path, months: int = 3):
    """Yield git log lines one at a time (streaming, no full materialization).

    Process execution lives in ``data/git_cli.stream_log_names``; this
    wrapper adds the repo pre-check that skips non-git sources without
    spawning anything. This is the default ``log_source`` for
    ``compute_git_scores``; tests inject a fake instead of patching by name.
    """
    if not _has_git(src):
        return
    yield from stream_log_names(src, months=months, timeout=_GIT_LOG_TIMEOUT_S)


def _accumulate_churn(
    file_set: set[str], src: Path, months: int,
    log_source: Callable[[Path, int], Iterable[str]],
) -> tuple[dict[str, int], dict[str, str]] | None:
    """Parse git log lines into per-file churn counts and last-touched dates.

    Returns None when the log stream yielded nothing (non-git source, or
    truly no history in the lookback window).
    """
    churn: dict[str, int] = {}
    last_date: dict[str, str] = {}
    current_date = ""
    has_lines = False
    for raw_line in log_source(src, months):
        has_lines = True
        line = raw_line.strip()
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
    if not has_lines:
        return None
    return churn, last_date


def _score_files_from_churn(
    files: list[str], churn: dict[str, int], last_date: dict[str, str], cfg: dict,
) -> dict[str, float]:
    """Convert per-file churn + last-touched date into churn/recency scores."""
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


def compute_git_scores(
    files: list[str],
    src: Path,
    config: dict | None = None,
    *,
    log_source: Callable[[Path, int], Iterable[str]] = _iter_git_log,
) -> dict[str, float]:
    """Layer 4: git churn and recency scoring."""
    cfg = config or {}
    file_set = set(files)
    accumulated = _accumulate_churn(
        file_set, src, cfg.get("git_lookback_months", 3), log_source,
    )
    if accumulated is None:
        return {}
    churn, last_date = accumulated
    return _score_files_from_churn(files, churn, last_date, cfg)
