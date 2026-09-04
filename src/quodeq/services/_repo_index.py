"""On-disk index backing ``find_existing_project``'s duplicate pre-flight check.

Finding (self-eval, Time Behaviour, major): ``find_existing_project`` did a
linear directory scan with a ``repository_info.json`` read per project
instead of an indexed lookup.

Mirrors performance-cycle1 Task 4's import-identity index
(``api/_import_identity.py`` + ``data/fs/project_index.py``): index-first
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
``_fs_project_helpers.find_existing_project``), so this index uses that same
three-field key rather than reusing a key scheme that doesn't match it.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from quodeq.core.observability import NULL_LOG, LogSink

_INDEX_FILENAME = ".repo_index.json"


def _repo_index_key(name: str, path: str, scope_path: str | None) -> str:
    """Stable string key for a (name, path, scopePath) identity tuple."""
    return f"{name}\x00{path}\x00{scope_path or ''}"


def _load_repo_index(reports_root: Path) -> dict[str, str]:
    """Load the repo-identity index, returning {} on a missing/corrupt file."""
    try:
        data = json.loads((reports_root / _INDEX_FILENAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_repo_index(reports_root: Path, index: dict[str, str], *, log: LogSink = NULL_LOG) -> None:
    """Write the repo-identity index atomically.

    Best-effort: a write failure is logged and swallowed, leaving
    ``find_existing_project``'s directory-walk fallback as the (slower,
    still-correct) path until a later successful write repairs the index.
    """
    tmp = ""
    try:
        fd, tmp = tempfile.mkstemp(dir=reports_root, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        os.replace(tmp, reports_root / _INDEX_FILENAME)
    except OSError as exc:
        log.warning(f"Could not save repo-identity index: {exc}")
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def add_repo_index_entry(
    reports_root: Path, name: str, path: str, scope_path: str | None, project_uuid: str,
    *, log: LogSink = NULL_LOG,
) -> None:
    """Register a newly-created project in the repo-identity index (best-effort)."""
    index = _load_repo_index(reports_root)
    index[_repo_index_key(name, path, scope_path)] = project_uuid
    _save_repo_index(reports_root, index, log=log)


def rekey_repo_index_entry(
    reports_root: Path, project_uuid: str, name: str, path: str, scope_path: str | None,
    *, log: LogSink = NULL_LOG,
) -> None:
    """Re-point a project's index entry at its changed repo identity.

    ``path`` is one third of the key, so a project whose stored path moves
    leaves the old key still mapped to its uuid. Drop every key pointing at
    the uuid, then register the new identity — one read-modify-write.

    Best-effort like the rest of this module: ``find_existing_project``
    verifies an index hit against the project's own record, so a failure
    here costs a directory walk, never a wrong answer.
    """
    index = _load_repo_index(reports_root)
    updated = {key: value for key, value in index.items() if value != project_uuid}
    updated[_repo_index_key(name, path, scope_path)] = project_uuid
    if updated != index:
        _save_repo_index(reports_root, updated, log=log)


def remove_repo_index_entries(
    reports_root: Path, project_uuids: set[str], *, log: LogSink = NULL_LOG,
) -> None:
    """Purge any index entries pointing at a deleted project (best-effort)."""
    if not project_uuids:
        return
    index = _load_repo_index(reports_root)
    remaining = {key: value for key, value in index.items() if value not in project_uuids}
    if len(remaining) != len(index):
        _save_repo_index(reports_root, remaining, log=log)
