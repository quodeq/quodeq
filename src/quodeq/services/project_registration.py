"""Use case: register a project (resolve identity, clone if needed, scan).

Extracted from ``evaluation_mixin`` so the API layer has a public entry
point instead of importing private helpers.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from quodeq.data.fs.project_files import read_repository_info, write_repository_info
from quodeq.data.git_cli import remote_origin_url_raw
from quodeq.data.fs.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.data.fs.repo_validation import validate_remote_url
from quodeq.services._fs_clone import run_git_clone
from quodeq.services._fs_scan import scan_project
from quodeq.shared._env import get_clones_dir
from quodeq.shared.utils import is_repo_url, project_name_from_repo

_LOCATION_LOCAL = "local"

# Mirrors _CREDENTIALS_RE in quodeq.api._evaluation_helpers. Not imported from
# there: services must not depend on the api layer (no other services module
# does), so the pattern is duplicated here rather than layered across.
# Userinfo cannot contain an unencoded "/", so excluding it keeps matches
# identical while a failing scan stays linear (no polynomial backtracking
# on inputs like repeated "http://" runs).
_CREDENTIALS_RE = re.compile(r"(https?://)([^/@]+)@")


def _strip_credentials(url: str) -> str:
    """Remove embedded userinfo (``user:pass@`` / ``token@``) from *url*.

    Only applies to scheme'd URLs (``https://user@host/...``). scp-style
    remotes (``git@github.com:org/repo.git``) are left untouched, since the
    leading ``git@`` there is a username convention, not a credential.
    """
    return _CREDENTIALS_RE.sub(r"\1", url)


def _scan_parent_project(project_dir: Path, reports_path: Path, repo_path: Path) -> None:
    """Scan the parent project directory if it lacks a scan.json."""
    info_path = project_dir / "repository_info.json"
    try:
        parent_uuid = json.loads(info_path.read_text(encoding="utf-8")).get("parent")
        if parent_uuid:
            parent_dir = reports_path / parent_uuid
            if not (parent_dir / "scan.json").exists():
                scan_project(repo_path, output_dir=parent_dir)
    except (json.JSONDecodeError, OSError):
        pass


def _read_origin_remote(repo_dir: Path) -> str | None:
    """Best-effort ``git remote get-url origin`` for a local working copy."""
    origin = remote_origin_url_raw(repo_dir)
    if not origin:
        return None
    return _strip_credentials(origin)


def register_project(
    repo: str,
    discipline: str | None,
    reports_dir: str,
    scope_path: str | None = None,
    *,
    clone_dest: str | None = None,
    ephemeral: bool = False,
    clones_dir: Path | None = None,
) -> str:
    """Resolve/register project and run a scan.

    For URL inputs, clones the repo before scanning. Either *clone_dest* (a
    user-chosen parent directory) or *ephemeral=True* must be set when *repo*
    is a URL. Ephemeral clones land under ``~/.quodeq/clones/<uuid>/`` by
    default; pass *clones_dir* to use a different (already-resolved) base
    directory instead of re-reading QUODEQ_CLONES_DIR here.

    For local path inputs, scans in place; *clone_dest* and *ephemeral* are
    ignored.

    Returns the project's UUID.
    """
    is_url = is_repo_url(repo)
    if is_url:
        # SSRF guard: reject private/loopback/link-local hosts before any clone
        # or directory side effects. Mirrors the CLI prepare_repository path so
        # the web API (POST /api/projects) cannot be pointed at internal hosts.
        validate_remote_url(repo)
    if is_url and not ephemeral and clone_dest is None:
        raise ValueError(
            "URL repos require either clone_dest (user-chosen path) or ephemeral=True"
        )
    if is_url and not ephemeral:
        dest = Path(clone_dest)
        if not dest.is_dir():
            raise FileNotFoundError(
                f"clone destination does not exist or is not a directory: {clone_dest}"
            )

    project_name = project_name_from_repo(repo)
    repo_resolved = repo if is_url else str(Path(repo).resolve())
    reports_path = Path(reports_dir)

    project_uuid = resolve_project_uuid(
        reports_path,
        ProjectIdentity(project_name, repo_resolved, discipline, _LOCATION_LOCAL, scope_path=scope_path),
    )
    project_dir = reports_path / project_uuid
    _ensure_onboarding_field(project_dir)

    # Resolve the on-disk path the project will live at.
    if is_url:
        if ephemeral:
            target_path = (clones_dir or get_clones_dir()) / project_uuid
        else:
            target_path = Path(clone_dest).resolve() / project_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # run_git_clone raises CloneError on failure (Task A8). We let it propagate.
        run_git_clone(repo, target_path)
    else:
        target_path = Path(repo_resolved)
        if not target_path.is_dir():
            # A path pointing at a FILE is a distinct user mistake from a
            # missing path (a real registration once slipped through as
            # .../lib/player.js) — say which one it was.
            detail = "points at a file, not a directory" if target_path.exists() else "does not exist"
            raise FileNotFoundError(f"Repo path {detail}: {target_path}")

    # Persist the resolved path + ephemeral flag in repository_info.json.
    # A corrupt existing file is treated as empty and rewritten (self-heal);
    # registration is the flow that owns this file's creation.
    info = read_repository_info(project_dir) or {}
    info["path"] = str(target_path.resolve())
    info["location"] = _LOCATION_LOCAL
    info["ephemeral"] = bool(ephemeral)
    origin_url = repo if is_url else _read_origin_remote(target_path)
    if origin_url:
        # Defense in depth: _read_origin_remote already strips credentials
        # from the local-remote branch, but strip again here so the
        # URL-registration branch (raw *repo*) is covered too, and so this
        # call site stays safe even if the helper's behavior changes.
        info["originUrl"] = _strip_credentials(origin_url)
    write_repository_info(project_dir, info)

    # Scan now that files are guaranteed on disk.
    scan_project(target_path, output_dir=project_dir)
    if scope_path:
        _scan_parent_project(project_dir, reports_path, target_path)

    return project_uuid


def _ensure_onboarding_field(project_dir: Path) -> None:
    """Add `onboardingCompletedAt: null` to repository_info.json if absent.

    Called from `register_project` so newly-registered projects start with the
    field set to null. Existing projects without the field get a backfill on
    read (see `_backfill_onboarding_field` in _fs_project_helpers.py).
    """
    data = read_repository_info(project_dir)
    if data is None or "onboardingCompletedAt" in data:
        return
    data["onboardingCompletedAt"] = None
    write_repository_info(project_dir, data)


def mark_onboarding_complete(project_dir: Path) -> None:
    """Stamp `onboardingCompletedAt` in repository_info.json if not already set.

    An existing timestamp is left untouched so re-evaluations don't move the
    original completion time.
    """
    data = read_repository_info(project_dir)
    if data is None or data.get("onboardingCompletedAt"):
        return
    data["onboardingCompletedAt"] = datetime.now(timezone.utc).isoformat()
    write_repository_info(project_dir, data)
