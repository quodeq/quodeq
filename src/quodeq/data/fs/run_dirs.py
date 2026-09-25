"""Run-directory removal and reports-root scanning.

Split out of ``services/_run_index_fs.py``: these two are plain filesystem
operations (rmtree, directory scan) with no run-index business logic of
their own, so they belong in the data layer. ``services/_run_index_fs.py``
re-exports both (via ``services/wiring.py``) for its existing callers.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.utils.io import is_within


def remove_run_directory(
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


def scan_reports_root_for_run(reports_root: Path | None, run_id: str) -> Path | None:
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
