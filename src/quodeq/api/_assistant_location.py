"""Session-scope resolution: run/repo-root lookups for the create-session and
tool-context routes, all jailed to the evaluations root or the shared clone.

Split out of _assistant_helpers.py (Task 10). ``get_evaluations_dir`` is
looked up on the ``_assistant_helpers`` facade at call time (rather than
imported directly here) so tests patching
"quodeq.api._assistant_helpers.get_evaluations_dir" keep working after the
split.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.utils.io import resolve_child_dir
from quodeq.services._fs_projects import get_project_info
from quodeq.services.shared_repo import shared_evaluations_root
from quodeq.services.shared_settings import read_settings


def resolve_run_location(project_id: str, run_id: str) -> tuple[str | None, str | None]:
    """Resolve ``(run_dir, repo_root)`` from a ``{projectId, runId}`` pair.

    Reuses the same layout the run index and project routes already rely on
    (see ``services/run_index.py``'s ``_walk_run_dirs`` and
    ``services/_fs_projects.get_project_info``): a run lives at
    ``<evaluations_root>/<project_id>/<run_id>`` where ``project_id`` is the
    directory name under ``get_evaluations_dir()`` (Plan-1's "project_uuid"),
    and the repo root is ``repository_info.json``'s ``path`` field, read via
    the existing ``get_project_info`` helper. Returns ``(None, None)`` when
    the run directory does not exist on disk.

    This is only called when the UI selects a SPECIFIC run. On the overview
    the UI sends no runId and the session stays run-unscoped; the assistant's
    detail tools then read the accumulated (per-dimension-latest) composition
    from ``project_id`` + ``reports_dir`` instead — matching the dashboard,
    which picks each dimension's latest run independently rather than binding
    one whole run.
    """
    from quodeq.api import _assistant_helpers as _helpers  # noqa: PLC0415 — deferred: see module docstring
    evaluations_root = Path(_helpers.get_evaluations_dir())
    # Resolve both segments against the directory listing rather than joining
    # and then jailing the result. A crafted project_id/run_id ("../..")
    # matches no entry, so there is nothing to contain afterwards. This
    # replaces the old resolve() + relative_to() + is_dir() sequence: those
    # three steps existed to undo a join we no longer perform.
    project_dir = resolve_child_dir(evaluations_root, project_id)
    run_dir = resolve_child_dir(project_dir, run_id) if project_dir else None
    if run_dir is None:
        return None, None
    return run_dir, resolve_repo_root(project_id)


def resolve_shared_run_location(project_id: str, run_id: str) -> str | None:
    """Shared-clone sibling of resolve_run_location: the run dir under the
    shared repo's evaluations root, jailed the same way (a crafted
    project_id/run_id must not escape the clone). Returns None when no shared
    repo is configured or the directory does not exist. Shared sessions never
    attach a repo root: the clone stores results, not a working copy, so
    unlike the local resolver this returns only the run dir.
    """
    settings = read_settings()
    if not settings.url:
        return None
    root = shared_evaluations_root(settings.url).resolve()
    project_dir = resolve_child_dir(root, project_id)
    run_dir = resolve_child_dir(project_dir, run_id) if project_dir else None
    if run_dir is None:
        return None
    return str(run_dir)


def repo_attach_info(project_id: str | None) -> tuple[str | None, str]:
    """(repo_root, reason) for the UI's attachment chip and write gate.

    Reasons: ok, no_project, unknown_project, no_recorded_path,
    online_project, path_missing."""
    from quodeq.api import _assistant_helpers as _helpers  # noqa: PLC0415 — deferred: see module docstring
    if not project_id:
        return None, "no_project"
    info = get_project_info(_helpers.get_evaluations_dir(), project_id)
    if info is None:
        return None, "unknown_project"
    path = info.get("path")
    if not path or not isinstance(path, str):
        return None, "no_recorded_path"
    if str(info.get("location", "")).lower() == "online" or "://" in path:
        return None, "online_project"
    if not Path(path).is_dir():
        return None, "path_missing"
    return path, "ok"


def resolve_repo_root(project_id: str) -> str | None:
    """Resolve the project's local working copy from ``project_id`` alone.

    The repo root is a PROJECT-level fact (``repository_info.json``'s
    ``path``), independent of any run: overview/accumulated sessions carry no
    ``runId`` yet still need repo access for the code-reading tools. Returns
    the path only when it is an existing local directory, so online projects
    (whose ``path`` is a URL) and moved/deleted working copies stay detached
    instead of carrying a bogus root. ``get_project_info`` jails the lookup
    to the evaluations root; the stored ``path`` itself is server-side data
    written at analysis time, never client input.
    """
    return repo_attach_info(project_id)[0]
