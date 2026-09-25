"""Single owner of the "is an evaluation actually running" rule.

The native window shell (dashboard/_webview_window) and the React
useRunningRunsRefresh hook both need to know whether a "running" job is
stale. The rule lives here, served by ``GET /api/evaluations/active``, so it
cannot diverge between presentation layers.

The rule:
a "running" job whose ``outputProject`` no longer exists in the project
list (project deleted, or the API restarted mid-scan) is stale and ignored.
Jobs without an ``outputProject`` are very-early-phase evals that haven't
registered an output yet and stay valid. Any failure building the project
list falls back to the first running job, so a transient glitch can't
accidentally suppress a real evaluation.
"""
from __future__ import annotations

from typing import Any

from quodeq.core.run.job_status import JobStatus
from quodeq.core.types import JobSnapshot
from quodeq.services.base import ActionProvider

# Providers hand back JobSnapshot entities, but remote/stub providers may
# return already-serialized wire dicts (the /api/evaluations route accepts
# both) — the accessors below read the same fields the webview shell used to
# read off the wire, including the legacy "project" key fallback.


def _read_field(item: Any, attr: str, *wire_keys: str) -> str | None:
    """*item*'s *attr* when it is an entity; for a wire dict, the first truthy
    of *wire_keys* (the last one's value, falsy or not, when none is)."""
    if not isinstance(item, dict):
        return getattr(item, attr, None)
    value = item.get(wire_keys[0])
    for key in wire_keys[1:]:
        value = value or item.get(key)
    return value


def _job_status(job: Any) -> str | None:
    return _read_field(job, "status", "status")


def _job_project(job: Any) -> str | None:
    return _read_field(job, "output_project", "outputProject", "project")


def _project_id(entry: Any) -> str | None:
    return _read_field(entry, "id", "id")


def find_active_evaluation(
    provider: ActionProvider, reports_dir: str,
) -> JobSnapshot | dict[str, Any] | None:
    """Return the first non-stale running evaluation job, or None.

    The job comes back exactly as the provider produced it (entity or wire
    dict); delivery layers serialize it the same way ``GET /api/evaluations``
    serializes its items.
    """
    items = provider.list_evaluations(reports_dir=reports_dir)
    running = [
        j for j in (items if isinstance(items, list) else [])
        if _job_status(j) == JobStatus.RUNNING
    ]
    if not running:
        return None
    try:
        data = provider.list_projects(reports_dir)
        projects = data.get("projects", []) if isinstance(data, dict) else []
        project_ids = {_project_id(p) for p in projects}
    except Exception:  # noqa: BLE001 - transient glitch in project list: fall back to first running job
        return running[0]
    for j in running:
        project = _job_project(j)
        # Jobs without an ``outputProject`` are very-early-phase evals that
        # haven't registered an output yet — keep treating those as valid.
        if not project or project in project_ids:
            return j
    return None
