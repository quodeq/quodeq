"""What a deleted project leaves outside its folder, and removing it.

A project's folder holds its runs, but two more traces of it live elsewhere in
the state directory: its score-cache rows (grades, History, the map's finding
payloads) and its standards settings under ``<quodeq dir>/projects/<id>``.

Both are keyed by project id, which a shared clone's projects share with
their pulled local copies, so they are removed only for a project deleted
from the LOCAL evaluations root.

The content-addressed result cache (``cache/results``) is deliberately not
touched: its entries are keyed by file content and path, not by project, so
another project with the same files reuses them.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.wiring import ScoreCacheError, forget_project_scores, remove_project_settings, settings_reports_root


def _is_local_root(reports_root: Path) -> bool:
    try:
        return reports_root.resolve() == settings_reports_root().resolve()
    except OSError:
        return False


def purge_project_leftovers(reports_root: Path, project_ids: Iterable[str], *, log: LogSink = NULL_LOG) -> None:
    """Drop the deleted *project_ids*' score-cache rows and settings folders (best-effort)."""
    ids = sorted(project_ids)
    if not ids or not _is_local_root(reports_root):
        return
    try:
        forget_project_scores(ids)
    except ScoreCacheError as exc:
        log.warning(f"Could not drop deleted projects' score cache rows: {exc}")
    for project_id in ids:
        try:
            remove_project_settings(project_id)
        except (OSError, ValueError) as exc:
            log.warning(f"Could not remove the settings of deleted project {project_id}: {exc}")
