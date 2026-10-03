"""The since-baseline summary the dashboard shows above the numbers.

A reduction of the run diff per dimension: the baseline chosen, then the
scoped block (majors delta, types closed and opened, new and resolved
counts, with its scope) and, labelled apart, the same numbers over every
file. The finding lists stay on the diff route.

Memoized per (project, run, version): a finished run's reports and the
project's suppressions are the only inputs that can change the answer, and
the dashboard is polled far more often than either changes.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from quodeq.core.run.state import TERMINAL_STATES, parse_run_state
from quodeq.services.run_diff import diff_runs
from quodeq.services.wiring import read_status
from quodeq.shared.log_throttle import LogThrottle

_logger = logging.getLogger(__name__)

_SCOPED_KEYS = ("scope", "changedFiles", "majorsDelta", "criticalDelta", "counts", "types")
_ACTIONS_LOG = "actions.jsonl"
_DELETED_FILE = "deleted.json"
_EVAL_DIR = "evaluation"
_KEY_STATE = "state"
_MEMO_SIZE = 32
# A report that cannot be read, a status the parser rejects, or a report
# whose shape is not the one the CLI writes: the dashboard renders without
# the summary rather than failing the request.
_UNREADABLE = (FileNotFoundError, OSError, ValueError, AttributeError, TypeError, KeyError)
# The same tuple also catches a programming error in diff_runs, so every
# catch is logged with its traceback, at most once a minute (polled route).
_UNREADABLE_LOG_INTERVAL_S = 60.0
_unreadable_log_throttle = LogThrottle(_UNREADABLE_LOG_INTERVAL_S)


def _reduce(entry: dict[str, Any]) -> dict[str, Any]:
    since = entry.get("sinceBaseline") or {}
    types = entry.get("types") or {}
    counts = entry.get("counts") or {}
    return {
        "againstRunId": entry.get("againstRunId"),
        "againstCommitSha": entry.get("againstCommitSha"),
        "sinceBaseline": {key: since.get(key) for key in _SCOPED_KEYS},
        "all": {
            "majorsDelta": entry.get("majorsDelta"),
            "criticalDelta": entry.get("criticalDelta"),
            "counts": {"new": counts.get("new", 0), "resolved": counts.get("resolved", 0)},
            "types": {"closed": types.get("closed") or [], "opened": types.get("opened") or []},
        },
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _version(project_dir: Path, run_dir: Path) -> tuple:
    """What can change the summary: the run's reports and the project's suppressions."""
    eval_dir = run_dir / _EVAL_DIR
    reports = tuple(sorted(
        (p.name, p.stat().st_mtime_ns) for p in eval_dir.iterdir() if p.is_file()
    )) if eval_dir.is_dir() else ()
    return (reports, _size(project_dir / _ACTIONS_LOG), _size(project_dir / _DELETED_FILE))


@lru_cache(maxsize=_MEMO_SIZE)
def _cached_summary(reports_root: str, project: str, run_id: str, version: tuple) -> dict[str, Any]:
    del version  # part of the key only
    diff = diff_runs(Path(reports_root), project, run_id, None)
    return {dim: _reduce(entry) for dim, entry in diff.get("dimensions", {}).items()}


def since_baseline_summary(reports_root: Path, project: str, run_id: str) -> dict[str, Any]:
    """Per-dimension summary for *run_id* against its default baselines; empty
    while the run is still in progress or when its reports cannot be read."""
    project_dir = reports_root / project
    run_dir = project_dir / run_id
    try:
        state = (read_status(run_dir) or {}).get(_KEY_STATE)
        if not state or parse_run_state(state) not in TERMINAL_STATES:
            return {}
        return _cached_summary(str(reports_root), project, run_id, _version(project_dir, run_dir))
    except _UNREADABLE:
        if _unreadable_log_throttle.should_emit(time.monotonic()):
            _logger.warning("since-baseline summary unavailable for %s/%s", project, run_id, exc_info=True)
        return {}


since_baseline_summary.cache_clear = _cached_summary.cache_clear  # type: ignore[attr-defined]
