"""Run-index housekeeping: directory removal, fallback scan, liveness, merge.

Split (Task 14 fix round) out of ``_evaluations_index.py``. Nothing patches
these directly (verified: no test reaches ``EvaluationsIndex`` internals by
name) so they move as plain free functions — no re-export required, callers
are ``EvaluationsIndex`` methods only. ``_evaluations_index.py`` is a
DECLARED_LOGGING_SITES entry; this sibling does not add a new logging
import, so ``_remove_run_directory`` takes an injected ``LogSink`` (the
caller already holds the facade's own declared logger and threads it
through).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.job import JobSnapshot
from quodeq.data.sqlite import run_index as _run_index
from quodeq.services._run_status_readers import _status_json_terminal
from quodeq.core.utils.io import is_within


def _merge_internal_jobs(
    snapshots: list[JobSnapshot], internal_jobs: list[JobSnapshot],
) -> list[JobSnapshot]:
    """Merge SQLite-index snapshots with in-memory internal jobs.

    Internal dashboard-spawned jobs always take priority over index rows
    that project the same on-disk run. The dedup key is (project, run_id)
    rather than job_id because internal jobs carry bare UUIDs while
    indexed rows carry "ext-<run_id>" — keying on job_id never matches
    the two views of the same run and both end up in the merged list.

    'lost' internal jobs are restart placeholders whose subprocess may
    still be alive: they must not shadow the truthful ext- row derived
    from the run's own status.json, and when such a row exists the
    placeholder itself is dropped in its favor.
    """
    covered = {
        (j.output_project, j.output_run_id) for j in internal_jobs
        if j.output_project and j.output_run_id and j.status != "lost"
    }
    row_keys = {
        (s.output_project, s.output_run_id) for s in snapshots
        if s.output_project and s.output_run_id
    }
    visible_internal = [
        j for j in internal_jobs
        if not (
            j.status == "lost"
            and (j.output_project, j.output_run_id) in row_keys
        )
    ]
    return [
        s for s in snapshots
        if (s.output_project, s.output_run_id) not in covered
    ] + visible_internal


def _remove_run_directory(
    reports_dir: Path, output_project: str | None, run_uuid: str,
    *, log: LogSink = NULL_LOG,
) -> bool:
    """Remove a run's on-disk directory. Returns True if removed.

    Tries the known project dir first (fast path when the snapshot carries
    ``output_project``); falls back to scanning every project dir under
    ``reports_dir`` for a ``run_uuid`` match.
    """
    removed_dir = False
    if output_project and reports_dir.is_dir():
        candidate = reports_dir / output_project / run_uuid
        if not is_within(candidate, reports_dir):
            candidate = None
        if candidate and candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
            removed_dir = not candidate.exists()
            if not removed_dir:
                log.warning(f"Could not remove run directory {candidate}")
    if not removed_dir and reports_dir.is_dir():
        for project_dir in reports_dir.iterdir():
            candidate = project_dir / run_uuid
            if not is_within(candidate, reports_dir):
                continue
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)
                removed_dir = not candidate.exists()
                if not removed_dir:
                    log.warning(f"Could not remove run directory {candidate}")
                break
    return removed_dir


def _scan_reports_root_for_run(reports_root: Path | None, run_id: str) -> Path | None:
    """Scan *reports_root* for ``<project>/<run_id>/``, jailed to *reports_root*."""
    if reports_root is None or not reports_root.is_dir():
        return None
    for project_dir in reports_root.iterdir():
        if not project_dir.is_dir():
            continue
        candidate = project_dir / run_id
        if not is_within(candidate, reports_root):
            continue
        if candidate.is_dir():
            return candidate
    return None


def _sync_external_run_by_scan(db, reports_dir: Path, run_id: str) -> None:
    """Fallback for an "ext-" id the index has no usable run_dir for yet.

    Scans every project dir under *reports_dir* for ``<project>/<run_id>``
    and syncs just that run when found; otherwise falls back to a full
    ``sync_index`` so a brand-new run still gets picked up. Once a run has
    been indexed once, ``get_status`` resolves it straight from its stored
    ``run_dir`` instead of reaching this scan again.
    """
    if reports_dir.is_dir():
        for project_dir in reports_dir.iterdir():
            candidate = project_dir / run_id
            if candidate.is_dir():
                _run_index.sync_index_for_run(db, candidate)
                return
    _run_index.sync_index(db, reports_dir)


def _external_job_is_complete(run_dir: Path) -> bool:
    """True when an external (``ext-``) job's *run_dir* shows it has ended."""
    if (run_dir / "scan.json").exists():
        return True
    if _status_json_terminal(run_dir):
        return True
    from quodeq.services._external_jobs import resolve_external_pid  # noqa: PLC0415
    pid_file = run_dir / ".pid"
    if not pid_file.exists():
        return True  # no PID file -> stale/crashed -> complete
    # run_dir is already resolved; pass its parent straight through
    # instead of splitting it into names and rejoining them.
    return resolve_external_pid(run_dir.parent, run_dir.name) is None
