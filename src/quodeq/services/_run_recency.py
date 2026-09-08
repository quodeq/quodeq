"""Order a project's run directories newest first.

Recency is ``started_at`` from each run's status.json (codebase convention),
falling back to directory mtime for runs that pre-date it, with the name as
the tie-break. Run ids are UUIDs, so a name sort alone would not do.

``started_at`` is written once with the run and never changes, so it is
remembered per run dir: the dismissed listing sorts every run on each request
and would otherwise re-read and re-parse every status.json each time. Only
found values are stored, so a run whose status.json is not there yet is
re-read on the next call. Bounded so a long-lived server cannot grow it
without limit.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services._wiring import file_mtime, read_run_status_json

_STARTED_AT_MEMO_MAX = 4096
_started_at_memo: dict[Path, str] = {}


def _run_started_at(run_dir: Path) -> str | None:
    started = _started_at_memo.get(run_dir)
    if started is not None:
        return started
    status = read_run_status_json(run_dir)
    # status.json is parsed unchecked; a valid-JSON non-dict must not turn
    # the listing into a 500, the run just loses its started_at ordering.
    started = status.get("started_at") if isinstance(status, dict) else None
    if not started:
        return None
    if len(_started_at_memo) >= _STARTED_AT_MEMO_MAX:
        _started_at_memo.clear()
    _started_at_memo[run_dir] = started = str(started)
    return started


def run_dirs_newest_first(project_dir: Path) -> list[Path]:
    """Run dirs that can hold finding detail (a projected DB or legacy
    ``evaluation/`` JSON), most recent first.

    The presence filter is evaluated live on purpose: a run gains its DB
    mid-scan, and only ``started_at`` is safe to remember.
    """
    def recency(run_dir: Path) -> tuple:
        started = _run_started_at(run_dir)
        if started:
            return (1, started, run_dir.name)
        return (0, file_mtime(run_dir) or 0.0, run_dir.name)

    candidates = [
        d for d in project_dir.iterdir()
        if d.is_dir() and ((d / "evaluation.db").is_file() or (d / "evaluation").is_dir())
    ]
    return sorted(candidates, key=recency, reverse=True)
