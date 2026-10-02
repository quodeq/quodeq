"""Shared progress plumbing for the connect, refresh and pull jobs.

Each job keeps a JobSlotStatus; these helpers write the sync fields the
status route exposes (phase, percent, bytes, projects_found) so the
Repositories tab can show one strip for every kind of sync.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from quodeq.core.observability import LogSink
from quodeq.core.types.sync_phase import SyncPhase
from quodeq.services.fs_project_helpers import max_projects_listed
from quodeq.services.fs_projects import collect_candidate_dirs
from quodeq.services.job_status import JobSlotStatus
from quodeq.services.wiring import ProgressUpdate
from quodeq.shared.fault_isolation import run_isolated

SYNC_IDLE_FIELDS: dict[str, object] = {
    "kind": None, "phase": None, "percent": None, "bytes": None, "projects_found": None,
}
_COUNT_EVERY = 10

# Hydrates the shared listing for (evaluations root, url); returns the project count.
WarmListing = Callable[[Path, str], int]


def progress_writer(status: JobSlotStatus) -> Callable[[ProgressUpdate], None]:
    """A callback that writes git progress into *status*, keeping the last known byte count."""
    def write(update: ProgressUpdate) -> None:
        fields: dict[str, object] = {"phase": SyncPhase.DOWNLOADING, "percent": update.percent}
        if update.bytes is not None:
            fields["bytes"] = update.bytes
        status.set(**fields)
    return write


def count_projects(eval_root: Path, status: JobSlotStatus) -> int:
    """Count project directories under *eval_root*, reporting the running count as READING."""
    status.set(phase=SyncPhase.READING, projects_found=0)
    if not eval_root.is_dir():
        return 0
    found = 0
    for found, _name in enumerate(collect_candidate_dirs(eval_root, max_projects_listed()), start=1):
        if found % _COUNT_EVERY == 0:
            status.set(projects_found=found)
    status.set(projects_found=found)
    return found


def _warm_isolated(eval_root: Path, url: str, warm: WarmListing, log: LogSink) -> None:
    run_isolated(lambda: warm(eval_root, url), label="shared listing warm-up", log=log)


def read_projects(
    eval_root: Path, url: str, status: JobSlotStatus, *, warm: WarmListing, log: LogSink,
) -> int:
    """The READING phase: count the projects, then hydrate the listing *warm* builds.

    The count lands first so the strip shows "N found" while the slow part
    runs (the hydration is one threaded pass, not per project, so the count
    cannot advance during it). A failed warm-up is logged and swallowed: the
    job still reaches DONE and the list route hydrates on demand, as before.
    """
    found = count_projects(eval_root, status)
    _warm_isolated(eval_root, url, warm, log)
    return found
