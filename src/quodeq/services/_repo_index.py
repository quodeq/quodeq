"""On-disk index backing ``find_existing_project``'s duplicate pre-flight check.

Why: without it ``find_existing_project`` would scan every project directory
and read each ``repository_info.json``; this index makes the duplicate check
a lookup.

Mirrors the import-identity index
(``services/project_import_identity.py`` + ``data/fs/project_index.py``): index-first
lookup, directory-walk fallback for entries the index doesn't have yet (a
project created before this index existed, or an index write that failed),
and self-heal -- a fallback hit is written back into the index so the next
lookup for that identity takes the fast path. Index staleness must never
produce a false negative: a miss always falls through to the walk.

This is a separate file from ``project_index.json`` (``data/fs/_index_io.py``):
that index is keyed by ``resolve_project_uuid``'s create-or-find identity,
which folds a scope_path into the child project's compound name.
``find_existing_project`` instead matches the literal ``name``/``path``/
``scopePath`` fields stored in ``repository_info.json`` (see
``fs_project_helpers.find_existing_project``), so this index uses that same
three-field key rather than reusing a key scheme that doesn't match it.
"""
from __future__ import annotations

import os  # noqa: F401 -- monkeypatched (module-attribute -> the shared os
# module) by tests/services/test_cluster32_empty_except_logging.py's
# save_repo_index cleanup-failure test; the actual os.replace/os.unlink
# calls are in data.fs.repo_index_store.write_repo_index, but patching
# THIS name still works since `import os` everywhere binds the same module.
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.wiring import read_repo_index as _read_repo_index_file
from quodeq.services.wiring import write_repo_index as _write_repo_index_file

_INDEX_FILENAME = ".repo_index.json"


def repo_index_key(name: str, path: str, scope_path: str | None) -> str:
    """Stable string key for a (name, path, scopePath) identity tuple."""
    return f"{name}\x00{path}\x00{scope_path or ''}"


@dataclass(frozen=True, slots=True)
class RepoIdentity:
    """The (name, path, scopePath) triple ``find_existing_project`` matches on.

    ``name`` is the bare project name derived from the repo, ``path`` the
    resolved local path or the URL as given, ``scope_path`` the optional
    sub-tree a scoped child project is registered for.
    """
    name: str
    path: str
    scope_path: str | None = None

    def key(self) -> str:
        """The index key for this identity (see ``repo_index_key``)."""
        return repo_index_key(self.name, self.path, self.scope_path)

    def matches_record(self, data: dict) -> bool:
        """True when a ``repository_info.json`` payload carries this identity.

        An empty or missing ``scopePath`` and a ``None`` scope compare equal.
        """
        return (
            data.get("name") == self.name
            and data.get("path") == self.path
            and (data.get("scopePath") or None) == (self.scope_path or None)
        )


def load_repo_index(reports_root: Path) -> dict[str, str]:
    """Load the repo-identity index, returning {} on a missing/corrupt file."""
    return _read_repo_index_file(reports_root / _INDEX_FILENAME)


def save_repo_index(reports_root: Path, index: dict[str, str], *, log: LogSink = NULL_LOG) -> None:
    """Write the repo-identity index atomically.

    Best-effort: a write failure is logged and swallowed, leaving
    ``find_existing_project``'s directory-walk fallback as the (slower,
    still-correct) path until a later successful write repairs the index.
    """
    try:
        _write_repo_index_file(reports_root / _INDEX_FILENAME, index, log=log)
    except OSError as exc:
        log.warning(f"Could not save repo-identity index: {exc}")


def add_repo_index_entry(
    reports_root: Path, identity: RepoIdentity, project_uuid: str,
    *, log: LogSink = NULL_LOG,
) -> None:
    """Register a newly-created project in the repo-identity index (best-effort)."""
    index = load_repo_index(reports_root)
    index[identity.key()] = project_uuid
    save_repo_index(reports_root, index, log=log)


def rekey_repo_index_entry(
    reports_root: Path, project_uuid: str, identity: RepoIdentity,
    *, log: LogSink = NULL_LOG,
) -> None:
    """Re-point a project's index entry at its changed repo identity.

    ``identity.path`` is one third of the key, so a project whose stored path moves
    leaves the old key still mapped to its uuid. Drop every key pointing at
    the uuid, then register the new identity — one read-modify-write.

    Best-effort like the rest of this module, but only up to a point:
    ``find_existing_project`` re-verifies an index hit against the project's
    own record for a local-unscoped identity, so a failure here costs a
    directory walk, never a wrong answer. URL and scoped identities skip
    that verification (their key and record disagree by construction) and
    trust the index, so for those a failure here can cost a wrong answer.
    """
    index = load_repo_index(reports_root)
    updated = {key: value for key, value in index.items() if value != project_uuid}
    updated[identity.key()] = project_uuid
    if updated != index:
        save_repo_index(reports_root, updated, log=log)


def remove_repo_index_entries(
    reports_root: Path, project_uuids: set[str], *, log: LogSink = NULL_LOG,
) -> None:
    """Purge any index entries pointing at a deleted project (best-effort)."""
    if not project_uuids:
        return
    index = load_repo_index(reports_root)
    remaining = {key: value for key, value in index.items() if value not in project_uuids}
    if len(remaining) != len(index):
        save_repo_index(reports_root, remaining, log=log)
