"""The dimensions of a project's most recent finished run.

The Evaluate setup card starts from them instead of an empty selection: the
user almost always re-runs what they ran last. Read from each run's
status.json, newest first; runs still going, failed or cancelled are skipped.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.run.state import RunState, UnsupportedSchemaError
from quodeq.services.wiring import list_runs, read_status

# How many recent runs to look through: the newest finished one is almost
# always among the first few.
_SCAN_LIMIT = 20


def latest_run_dimensions(reports_root: Path, project: str, *, log: LogSink = NULL_LOG) -> list[str]:
    """The newest finished run's dimension ids, or [] when there is none."""
    for run in list_runs(reports_root, project, limit=_SCAN_LIMIT):
        # The state comes from status.json itself: list_runs reports a run
        # it has no index row for as done, which a running run is not.
        try:
            status = read_status(reports_root / project / run.run_id) or {}
        except (UnsupportedSchemaError, OSError) as exc:
            # A run written by a newer CLI, or unreadable: the preselection
            # is optional, so skip it rather than fail project info.
            log.info(f"skipping run {run.run_id} for the last-run dimensions: {exc}")
            continue
        if status.get("state") != RunState.DONE:
            continue
        dims = status.get("dimensions")
        if isinstance(dims, list) and dims:
            return [str(d) for d in dims]
    return []
