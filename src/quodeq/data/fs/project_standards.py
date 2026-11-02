"""Machine-local per-project standards settings.

Each project's settings live at ``<quodeq dir>/projects/<owner>/standards.json``;
a scoped child project shares its parent's file. The legacy repo files
(``.quodeq/standards-visibility.json`` and ``standards-overrides.json``) are
read once, to seed a new settings file, and are never written or deleted.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path, PureWindowsPath

from quodeq.core.standards.visibility import DEFAULT_VISIBLE_STANDARDS, normalize_ids
from quodeq.data.fs.legacy_standards_files import legacy_repo_overrides, legacy_repo_visibility
from quodeq.data.fs.project_files import read_repository_info
from quodeq.data.locking import get_file_lock
from quodeq.shared.advisory_json import read_advisory_json
from quodeq.shared.env_paths import get_evaluations_dir, get_quodeq_dir
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)

SETTINGS_VERSION = 2
_PROJECTS_DIRNAME = "projects"
_SETTINGS_FILENAME = "standards.json"
_LOCK_FILENAME = "standards.lock"


@dataclass(frozen=True)
class ProjectStandards:
    """One project's standards settings: which standards are on, and overrides.

    ``enabled=None`` means "never chosen": the ISO defaults apply. An empty
    tuple is a real selection (nothing enabled).
    """

    enabled: tuple[str, ...] | None = None
    overrides: Mapping[str, dict] = field(default_factory=dict)
    migrated_from: str | None = None

    @property
    def visible_ids(self) -> tuple[str, ...]:
        """The standards that are on: the explicit selection, else the ISO defaults."""
        return DEFAULT_VISIBLE_STANDARDS if self.enabled is None else self.enabled

    @property
    def is_default(self) -> bool:
        """True when no selection was ever saved."""
        return self.enabled is None


def settings_reports_root(env: Mapping[str, str] | None = None) -> Path:
    """The LOCAL evaluations root every settings reader resolves owners under.

    A scoped child's ``parent`` is read only from here, never from a shared
    clone's reports root, so the API, the assistant and the dashboard all
    resolve one project to the same settings file.
    """
    return Path(get_evaluations_dir(env=dict(env) if env is not None else None))


def is_safe_owner_id(value: object) -> bool:
    """True when *value* is one plain path segment (no separator, traversal or drive)."""
    if not isinstance(value, str) or value in ("", "."):
        return False
    try:
        validate_path_segment(value)
    except ValueError:
        return False
    return not (Path(value).is_absolute() or PureWindowsPath(value).drive)


def settings_file_for_owner(owner_id: str, *, env: Mapping[str, str] | None = None) -> Path:
    """``<quodeq dir>/projects/<owner_id>/standards.json``.

    Raises ``ValueError`` when *owner_id* is not a single safe path segment,
    so no id can place the file outside the projects dir.
    """
    if not is_safe_owner_id(owner_id):
        raise ValueError(f"Invalid project id for standards settings: {owner_id!r}")
    return get_quodeq_dir(env) / _PROJECTS_DIRNAME / owner_id / _SETTINGS_FILENAME


def remove_project_settings(project_id: str, *, env: Mapping[str, str] | None = None) -> bool:
    """Delete a deleted project's own settings folder; True when one was there.

    A scoped child has no folder of its own (it uses its parent's), so this
    never touches another project's settings.
    """
    folder = settings_file_for_owner(project_id, env=env).parent
    if folder.is_symlink():
        folder.unlink()
        return True
    if not folder.is_dir():
        return False
    shutil.rmtree(folder)
    return True


@contextmanager
def _settings_lock(target: Path) -> Iterator[None]:
    """Hold the cross-process lock that guards *target* (a sidecar lock file)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = get_file_lock()
    with open(target.with_name(_LOCK_FILENAME), "ab+") as fh:
        lock.acquire(fh)
        try:
            yield
        finally:
            lock.release(fh)


def _clean_overrides(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    return {req: vals for req, vals in raw.items() if isinstance(req, str) and isinstance(vals, dict)}


def read_project_standards(path: Path) -> ProjectStandards:
    """The settings at *path*; defaults when absent or malformed (never raises)."""
    data, err = read_advisory_json(path)
    if err is not None:
        _logger.warning("Ignoring unreadable or malformed standards settings %s: %s", path, err)
        return ProjectStandards()
    if data is None:
        return ProjectStandards()
    if not isinstance(data, dict):
        _logger.warning("Ignoring standards settings %s: not a JSON object", path)
        return ProjectStandards()
    raw_enabled = data.get("enabled")
    if raw_enabled is not None and not isinstance(raw_enabled, list):
        _logger.warning("Ignoring 'enabled' in standards settings %s: not a list", path)
    enabled = normalize_ids(raw_enabled) if isinstance(raw_enabled, list) else None
    origin = data.get("migratedFrom")
    return ProjectStandards(
        enabled=enabled,
        overrides=_clean_overrides(data.get("overrides")),
        migrated_from=origin if isinstance(origin, str) else None,
    )


def write_project_standards(path: Path, standards: ProjectStandards) -> None:
    """Atomically write *standards* to *path*, creating parent dirs."""
    payload: dict[str, object] = {"version": SETTINGS_VERSION, "overrides": dict(standards.overrides)}
    if standards.enabled is not None:
        payload["enabled"] = list(standards.enabled)
    if standards.migrated_from:
        payload["migratedFrom"] = standards.migrated_from
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".standards-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if tmp is not None:
            Path(tmp).unlink(missing_ok=True)
        raise


def load_overrides_file(path: Path | None) -> dict[str, dict]:
    """Overrides from a settings file; ``{}`` for None, absent or malformed."""
    if path is None:
        return {}
    return dict(read_project_standards(path).overrides)


def settings_owner_id(reports_root: Path | None, project_id: str) -> str:
    """The id whose settings *project_id* uses: a scoped child's parent, else itself."""
    if reports_root is None:
        return project_id
    info = read_repository_info(Path(reports_root) / project_id)
    parent = info.get("parent") if isinstance(info, dict) else None
    if parent is None or parent == "":
        return project_id
    if not is_safe_owner_id(parent):
        _logger.warning("Ignoring unsafe parent %r in %s's repository info", parent, project_id)
        return project_id
    return parent


def _recorded_repo_root(reports_root: Path | None, project_id: str) -> Path | None:
    """The project's local working copy, when it has one that still exists."""
    if reports_root is None:
        return None
    info = read_repository_info(Path(reports_root) / project_id)
    path = info.get("path") if isinstance(info, dict) else None
    if not isinstance(path, str) or "://" in path or path.startswith("git@"):
        return None
    root = Path(path)
    return root if root.is_dir() else None


def _migration_seed(
    reports_root: Path | None, owner: str, repo_root: Path | None,
) -> ProjectStandards | None:
    """The settings the legacy repo files hold, or None when there are none.

    Read from *repo_root* (a run's source) or else the recorded working copy.
    ``migratedFrom`` names the recorded working copy only: an explicit
    *repo_root* may be a temp clone or worktree that is gone after the run.
    """
    recorded = _recorded_repo_root(reports_root, owner)
    source = repo_root or recorded
    if source is None:
        return None
    visible = legacy_repo_visibility(source)
    overrides = legacy_repo_overrides(source)
    if visible is None and not overrides:
        return None
    return ProjectStandards(
        enabled=visible, overrides=overrides,
        migrated_from=str(recorded) if recorded is not None else None)


def _seed_if_absent(target: Path, seed: ProjectStandards) -> None:
    """Write *seed* unless a settings file appeared meanwhile. Caller holds the lock."""
    if target.is_file():
        return
    write_project_standards(target, seed)
    _logger.info("standards settings migrated from %s to %s", seed.migrated_from or "the run source", target)


def project_settings_file(
    reports_root: Path | None, project_id: str, *,
    repo_root: Path | None = None, env: Mapping[str, str] | None = None,
    migrate: bool = True,
) -> Path:
    """The settings file for *project_id*, migrating legacy repo files on first use.

    The legacy files are read outside the lock; the write happens under it,
    after re-checking that no save created the file meanwhile.
    ``migrate=False`` is for read-only resolvers (estimates, the findings
    server subprocess): they resolve the owner's path and never write.
    """
    owner = settings_owner_id(reports_root, project_id)
    target = settings_file_for_owner(owner, env=env)
    if migrate and not target.is_file():
        seed = _migration_seed(reports_root, owner, repo_root)
        if seed is not None:
            with _settings_lock(target):
                _seed_if_absent(target, seed)
    return target


def load_project_standards(
    reports_root: Path | None, project_id: str | None, *,
    repo_root: Path | None = None, env: Mapping[str, str] | None = None,
) -> ProjectStandards:
    """*project_id*'s settings; defaults when there is no project or no file."""
    if not project_id:
        return ProjectStandards()
    return read_project_standards(
        project_settings_file(reports_root, project_id, repo_root=repo_root, env=env))


def _update_settings(
    reports_root: Path | None, project_id: str,
    change: Callable[[ProjectStandards], ProjectStandards],
    env: Mapping[str, str] | None,
) -> ProjectStandards:
    """Read, change and write *project_id*'s settings under the file's lock."""
    path = project_settings_file(reports_root, project_id, env=env)
    with _settings_lock(path):
        updated = change(read_project_standards(path))
        write_project_standards(path, updated)
    return updated


def save_enabled_ids(
    reports_root: Path | None, project_id: str, ids: list[str], *,
    env: Mapping[str, str] | None = None,
) -> ProjectStandards:
    """Replace the enabled list, keeping overrides. Returns what was written."""
    enabled = normalize_ids(ids)
    return _update_settings(reports_root, project_id, lambda cur: replace(cur, enabled=enabled), env)


def save_overrides(
    reports_root: Path | None, project_id: str, overrides: Mapping[str, dict], *,
    env: Mapping[str, str] | None = None,
) -> ProjectStandards:
    """Replace the overrides (``{}`` clears them), keeping the enabled list."""
    clean = dict(overrides)
    return _update_settings(reports_root, project_id, lambda cur: replace(cur, overrides=clean), env)
