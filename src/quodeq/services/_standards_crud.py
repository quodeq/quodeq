"""CRUD and import operations for custom standards.

Every filesystem touch — existence, path composition, mkdir, unlink,
payload read/write — goes through the injected :class:`StandardsStore`
seam (see ``services/ports.py``); the functions here keep the validation
and permission rules (managed/builtin/collision).
"""
from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from quodeq.core.types.standard import StandardDetail
from quodeq.services.ports import StandardsStore
from quodeq.services._standards_io import (
    _TYPE_CUSTOM, build_custom_meta, build_detail, count_principles_and_requirements,
)
from quodeq.services.import_validator import validate_import, scan_injection

_CUSTOM_DEFAULTS = {"type": _TYPE_CUSTOM, "managed": False, "origin": None, "origin_hash": None}


def _validate_id(standard_id: str) -> None:
    if not standard_id or "/" in standard_id or "\\" in standard_id or ".." in standard_id or os.sep in standard_id:
        raise ValueError(f"Invalid standard ID: {standard_id}")


def create(data: dict, evaluators_dir: Path, store: StandardsStore) -> StandardDetail:
    """Create a new custom standard and persist it to disk."""
    standard_id = data["id"]
    _validate_id(standard_id)
    path = store.path(evaluators_dir, standard_id)
    if store.exists(evaluators_dir, standard_id):
        raise ValueError(f"Standard '{standard_id}' already exists")
    store.ensure_dir(evaluators_dir)
    store.write(path, {**data, **_CUSTOM_DEFAULTS})
    return build_detail(store.read(path))


def update(standard_id: str, data: dict, evaluators_dir: Path, store: StandardsStore) -> StandardDetail:
    """Update an existing custom standard with new *data*."""
    _validate_id(standard_id)
    path = store.path(evaluators_dir, standard_id)
    if not store.exists(evaluators_dir, standard_id):
        raise FileNotFoundError(f"Standard not found: {standard_id}")
    if store.read(path).get("managed", False):
        raise PermissionError(f"Cannot edit managed standard '{standard_id}'")
    payload = {**data, "id": standard_id, "type": _TYPE_CUSTOM, "managed": False}
    store.write(path, payload)
    return build_detail(payload)


def delete(standard_id: str, evaluators_dir: Path, compiled_dir: Path,
           store: StandardsStore, is_builtin: Callable[[str], bool]) -> None:
    """Delete a custom standard. Raises for built-in or managed standards."""
    _validate_id(standard_id)
    path = store.path(evaluators_dir, standard_id)
    if not store.exists(evaluators_dir, standard_id):
        if store.compiled_exists(compiled_dir, standard_id) or is_builtin(standard_id):
            raise PermissionError(f"Cannot delete built-in standard '{standard_id}'")
        raise FileNotFoundError(f"Standard not found: {standard_id}")
    if store.read(path).get("managed", False):
        raise PermissionError(f"Cannot delete managed standard '{standard_id}'")
    store.remove(evaluators_dir, standard_id)


def duplicate(standard_id: str, new_id: str, source_detail: StandardDetail,
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
    store.write(new_path, payload)
    return build_detail(store.read(new_path))


def import_from_file(data: dict, force: bool, evaluators_dir: Path, store: StandardsStore) -> dict:
    """Import an evaluator from parsed file data."""
    validation = validate_import(data)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    cleaned = validation["data"]
    warnings = scan_injection(cleaned)
    standard_id = cleaned["id"]
    path = store.path(evaluators_dir, standard_id)
    if store.exists(evaluators_dir, standard_id) and not force:
        existing = store.read(path)
        p, r = count_principles_and_requirements(existing)
        return {"status": "conflict", "detail": None,
                "existing": build_custom_meta(existing, p, r), "warnings": warnings}
    if store.exists(evaluators_dir, standard_id) and force and store.read(path).get("managed", False):
        raise PermissionError(f"Cannot overwrite managed standard '{standard_id}'")
    store.ensure_dir(evaluators_dir)
    store.write(path, {**cleaned, **_CUSTOM_DEFAULTS})
    return {"status": "imported", "detail": build_detail(store.read(path)),
            "existing": None, "warnings": warnings}
