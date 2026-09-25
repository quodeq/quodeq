"""CRUD and import operations for custom standards.

Every filesystem touch — existence, path composition, mkdir, unlink,
payload read/write — goes through the injected :class:`StandardsStore`
seam (see ``services/ports.py``); the functions here keep the validation
and permission rules (managed/builtin/collision).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from quodeq.core.types.standard import StandardDetail
from quodeq.services.ports import StandardNotFoundError, StandardProtectedError, StandardsStore
from quodeq.services._standards_io import (
    TYPE_CUSTOM, build_custom_meta, build_detail, count_principles_and_requirements,
)
from quodeq.services.import_validator import (
    StandardImportValidationError, validate_import, scan_injection,
)

_CUSTOM_DEFAULTS = {"type": TYPE_CUSTOM, "managed": False, "origin": None, "origin_hash": None}

# import_from_file()'s result["status"] on a name collision with an existing
# standard id (its other value, "imported", is not branched on by callers).
# Re-exported by services/standards.py: api and assistant import it from
# there (they may not reach into this private module).
IMPORT_STATUS_CONFLICT = "conflict"


def _write_and_load_detail(store: StandardsStore, path: Path, payload: dict) -> StandardDetail:
    """Persist *payload* at *path* and build the detail from what the store reads back."""
    store.write(path, payload)
    return build_detail(store.read(path))


_ID_PATH_TOKENS = ("/", "\\", "..")
"""Anything that would let a standard id escape the evaluators directory.

``os.sep`` needs no separate clause: it is ``/`` or ``\\`` on every platform
Python runs on, and both are already listed.
"""


def _validate_id(standard_id: str) -> None:
    """Reject an empty id, or one that could traverse out of the standards dir."""
    if not standard_id or any(token in standard_id for token in _ID_PATH_TOKENS):
        raise ValueError(f"Invalid standard ID: {standard_id}")


def create(data: dict, evaluators_dir: Path, store: StandardsStore) -> StandardDetail:
    """Create a new custom standard and persist it to disk."""
    standard_id = data["id"]
    _validate_id(standard_id)
    path = store.path(evaluators_dir, standard_id)
    if store.exists(evaluators_dir, standard_id):
        raise ValueError(f"Standard '{standard_id}' already exists")
    store.ensure_dir(evaluators_dir)
    return _write_and_load_detail(store, path, {**data, **_CUSTOM_DEFAULTS})


def update(standard_id: str, data: dict, evaluators_dir: Path, store: StandardsStore) -> StandardDetail:
    """Update an existing custom standard with new *data*."""
    _validate_id(standard_id)
    path = store.path(evaluators_dir, standard_id)
    if not store.exists(evaluators_dir, standard_id):
        raise StandardNotFoundError(f"Standard not found: {standard_id}")
    if store.read(path).get("managed", False):
        raise StandardProtectedError(f"Cannot edit managed standard '{standard_id}'")
    payload = {**data, "id": standard_id, "type": TYPE_CUSTOM, "managed": False}
    store.write(path, payload)
    return build_detail(payload)


def delete(standard_id: str, evaluators_dir: Path, compiled_dir: Path,
           store: StandardsStore, is_builtin: Callable[[str], bool]) -> None:
    """Delete a custom standard. Raises for built-in or managed standards."""
    _validate_id(standard_id)
    path = store.path(evaluators_dir, standard_id)
    if not store.exists(evaluators_dir, standard_id):
        if store.compiled_exists(compiled_dir, standard_id) or is_builtin(standard_id):
            raise StandardProtectedError(f"Cannot delete built-in standard '{standard_id}'")
        raise StandardNotFoundError(f"Standard not found: {standard_id}")
    if store.read(path).get("managed", False):
        raise StandardProtectedError(f"Cannot delete managed standard '{standard_id}'")
    store.remove(evaluators_dir, standard_id)


def duplicate(new_id: str, source_detail: StandardDetail,
              evaluators_dir: Path, store: StandardsStore) -> StandardDetail:
    """Duplicate an existing standard under *new_id* as a custom copy."""
    _validate_id(new_id)
    new_path = store.path(evaluators_dir, new_id)
    if store.exists(evaluators_dir, new_id):
        raise ValueError(f"Standard '{new_id}' already exists")
    store.ensure_dir(evaluators_dir)
    s = source_detail
    payload = {"id": new_id, "name": s.name, "description": s.description,
               "weight": s.weight, "source": s.source, "principles": s.principles,
               **_CUSTOM_DEFAULTS}
    return _write_and_load_detail(store, new_path, payload)


def import_from_file(data: dict, force: bool, evaluators_dir: Path, store: StandardsStore) -> dict:
    """Import an evaluator from parsed file data."""
    validation = validate_import(data)
    if not validation["valid"]:
        # Typed, with the reasons attached: the API route reports them from
        # the error instead of re-running the validator in its except block,
        # which misread every later ValueError as a schema failure.
        raise StandardImportValidationError(validation["errors"])
    cleaned = validation["data"]
    warnings = scan_injection(cleaned)
    standard_id = cleaned["id"]
    path = store.path(evaluators_dir, standard_id)
    existing = store.read(path) if store.exists(evaluators_dir, standard_id) else None
    if existing is not None and not force:
        p, r = count_principles_and_requirements(existing)
        return {"status": IMPORT_STATUS_CONFLICT, "detail": None,
                "existing": build_custom_meta(existing, p, r), "warnings": warnings}
    if existing is not None and existing.get("managed", False):
        raise StandardProtectedError(f"Cannot overwrite managed standard '{standard_id}'")
    store.ensure_dir(evaluators_dir)
    detail = _write_and_load_detail(store, path, {**cleaned, **_CUSTOM_DEFAULTS})
    return {"status": "imported", "detail": detail,
            "existing": None, "warnings": warnings}
