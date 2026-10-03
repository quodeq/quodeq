"""Session-scope resolution: run/repo-root lookups for the create-session and
tool-context routes, all jailed to the evaluations root or the shared clone.

``get_evaluations_dir`` is imported from its real owner
(``quodeq.shared.env``), never from the ``_assistant_helpers`` facade, so this
module never imports back the facade that re-exports it. ``get_repository``
lives here so ``_assistant_hygiene.py`` can import it without cycling back
through the facade.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from quodeq.assistant import AssistantRepository, AssistantStore
from quodeq.core.utils.io import resolve_child_dir
from quodeq.services.fs_projects import get_project_info, repo_attach_reason
from quodeq.services.shared_repo import shared_evaluations_root
from quodeq.services.shared_settings import read_settings
from quodeq.shared.env import get_evaluations_dir


def _run_dir_under(root: str | Path, project_id: str, run_id: str) -> str | None:
    """``<root>/<project_id>/<run_id>`` when both directories exist, else None.

    Both segments are matched against the directory listing rather than
    joined and then jailed, so a crafted id ("../..") matches no entry and
    there is nothing to contain afterwards.
    """
    project_dir = resolve_child_dir(root, project_id)
    return resolve_child_dir(project_dir, run_id) if project_dir else None


def resolve_run_location(project_id: str, run_id: str) -> tuple[str | None, str | None]:
    """Resolve ``(run_dir, repo_root)`` from a ``{projectId, runId}`` pair.

    Reuses the same layout the run index and project routes already rely on
    (see ``services/run_index.py``'s ``_walk_run_dirs`` and
    ``services/fs_projects.get_project_info``): a run lives at
    ``<evaluations_root>/<project_id>/<run_id>`` where ``project_id`` is the
    directory name under ``get_evaluations_dir()`` (the session row calls it
    "project_uuid"),
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
    run_dir = _run_dir_under(Path(get_evaluations_dir()), project_id, run_id)
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
    run_dir = _run_dir_under(shared_evaluations_root(settings.url).resolve(), project_id, run_id)
    if run_dir is None:
        return None
    return str(run_dir)


def repo_attach_info(project_id: str | None) -> tuple[str | None, str]:
    """(repo_root, reason) for the UI's attachment chip and write gate.

    Reasons: ok, no_project, unknown_project, no_recorded_path,
    online_project, path_missing. The project_id-level reasons are handled
    here; repo_attach_reason (shared with services.local_repo_root) covers
    the rest once a project's info is resolved."""
    if not project_id:
        return None, "no_project"
    info = get_project_info(get_evaluations_dir(), project_id)
    if info is None:
        return None, "unknown_project"
    path, reason = repo_attach_reason(info)
    return path, reason


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


def get_repository(app: Flask) -> AssistantStore:
    """The app-wide ``AssistantStore``, built once and cached on *app*."""
    if not hasattr(app, "_assistant_repository"):
        app._assistant_repository = AssistantRepository(
            Path(app.config["ASSISTANT_DB_PATH"])
        )
    return app._assistant_repository
