"""Refresh a registered project's working copy from its git remote.

Owns the checks around the data-layer refresh: the project must have a
remote and a folder, nothing may be evaluating that folder, and the fetch
runs under the same DNS pin and access env a clone of that remote gets.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.config.clone_env import git_clone_timeout_s
from quodeq.core.run.job_status import JobStatus
from quodeq.core.types.working_copy_refresh import RefreshOutcome
from quodeq.services._fs_working_copy import derive_last_fetched_at
from quodeq.services.base import ActionProvider
from quodeq.services.github_access import refresh_access_env
from quodeq.services.wiring import RefreshResult, pinned_git_config, refresh_working_copy, remote_origin_url_raw

_in_flight: set[str] = set()
_in_flight_guard = threading.Lock()


@dataclass(frozen=True)
class RefreshDeps:
    """The collaborators ``refresh_project`` drives; tests replace them."""

    refresh: Callable[..., RefreshResult] = refresh_working_copy
    live_remote: Callable[[str], str | None] = remote_origin_url_raw
    pin: Callable[[str], Sequence[str]] = pinned_git_config
    access_env: Callable[[str], Mapping[str, str] | None] = refresh_access_env


@dataclass(frozen=True)
class ProjectRefresh:
    """Outcome of ``refresh_project``. *last_fetched_at* is ISO-8601, set on success."""

    outcome: RefreshOutcome
    new_commits: int = 0
    detail: str = ""
    last_fetched_at: str | None = None


def _same_folder(a: str | None, b: str) -> bool:
    return bool(a) and Path(a).resolve() == Path(b).resolve()


def _evaluating(provider: ActionProvider, reports_dir: str, project: str, path: str) -> bool:
    """True when a running evaluation reads *path*: this project's own, or a
    scoped sibling's that shares the checkout."""
    for job in provider.list_evaluations(reports_dir=reports_dir):
        if job.status != JobStatus.RUNNING or not job.output_project:
            continue
        if job.output_project == project:
            return True
        other = provider.get_project_info(reports_dir, job.output_project) or {}
        if _same_folder(other.get("path"), path):
            return True
    return False


def _fetch(info: Mapping[str, Any], path: str, deps: RefreshDeps) -> RefreshResult:
    origin = info["originUrl"]
    try:
        git_config = deps.pin(deps.live_remote(path) or origin)
    except ValueError as exc:
        return RefreshResult(RefreshOutcome.FETCH_FAILED, detail=str(exc))
    return deps.refresh(
        Path(path), hard_reset=bool(info.get("ephemeral")), timeout_s=git_clone_timeout_s(),
        env=deps.access_env(origin), git_config=git_config,
    )


def refresh_project(
    provider: ActionProvider, reports_dir: str, project: str, *, deps: RefreshDeps | None = None,
) -> ProjectRefresh | None:
    """Refresh *project*'s working copy. None when the project does not exist.

    A clone quodeq manages (``ephemeral``) is reset onto the remote branch;
    any other folder is only fast-forwarded from a clean tree.
    """
    deps = deps or RefreshDeps()
    info = provider.get_project_info(reports_dir, project)
    if not info:
        return None
    path = info.get("path")
    if not info.get("originUrl") or not path or not Path(path).is_dir():
        return ProjectRefresh(RefreshOutcome.NOT_REFRESHABLE)
    key = str(Path(path).resolve())
    with _in_flight_guard:
        if key in _in_flight:
            return ProjectRefresh(RefreshOutcome.BUSY)
        _in_flight.add(key)
    try:
        if _evaluating(provider, reports_dir, project, path):
            return ProjectRefresh(RefreshOutcome.BUSY)
        result = _fetch(info, path, deps)
    finally:
        with _in_flight_guard:
            _in_flight.discard(key)
    return ProjectRefresh(
        result.outcome, result.new_commits, result.detail, derive_last_fetched_at(path),
    )
