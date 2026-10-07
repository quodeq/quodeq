"""The dimensions of a project's most recent finished run.

The Evaluate setup card starts from them instead of an empty selection: the
user almost always re-runs what they ran last. Read from each run's
status.json, newest first; runs still going, failed or cancelled are skipped.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.run.state import RunState
from quodeq.data.fs.run_status_store import read_status
from quodeq.services.wiring import list_runs

# How many recent runs to look through: the newest finished one is almost
# always among the first few.
_SCAN_LIMIT = 20


def latest_run_dimensions(reports_root: Path, project: str) -> list[str]:
    """The newest finished run's dimension ids, or [] when there is none."""
    for run in list_runs(reports_root, project, limit=_SCAN_LIMIT):
        # The state comes from status.json itself: list_runs reports a run
        # it has no index row for as done, which a running run is not.
        status = read_status(reports_root / project / run.run_id) or {}
        if status.get("state") != RunState.DONE:
            continue
        dims = status.get("dimensions")
        if isinstance(dims, list) and dims:
            return [str(d) for d in dims]
    return []
