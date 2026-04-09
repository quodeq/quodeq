"""CRUD and import operations for custom standards."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.types.standard import StandardDetail
from quodeq.services._standards_io import (
    _TYPE_CUSTOM, build_custom_meta, build_detail, count_principles_and_requirements,
)
from quodeq.services.import_validator import validate_import, scan_injection

_CUSTOM_DEFAULTS = {"type": _TYPE_CUSTOM, "managed": False, "origin": None, "origin_hash": None}


@dataclass
class JsonIO:
    """Grouped JSON read/write callables."""

    read: Callable
    write: Callable


def _validate_id(standard_id: str) -> None:
    if not standard_id or "/" in standard_id or "\\" in standard_id or ".." in standard_id or os.sep in standard_id:
        raise ValueError(f"Invalid standard ID: {standard_id}")


def create(data: dict, evaluators_dir: Path, io: JsonIO) -> StandardDetail:
    """Create a new custom standard and persist it to disk."""
    standard_id = data["id"]
    _validate_id(standard_id)
    path = evaluators_dir / f"{standard_id}.json"
    if path.exists():
        raise ValueError(f"Standard '{standard_id}' already exists")
    evaluators_dir.mkdir(parents=True, exist_ok=True)
    io.write(path, {**data, **_CUSTOM_DEFAULTS})
    return build_detail(io.read(path))


def update(standard_id: str, data: dict, evaluators_dir: Path, io: JsonIO) -> StandardDetail:
    """Update an existing custom standard with new *data*."""
    path = evaluators_dir / f"{standard_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Standard not found: {standard_id}")
    if io.read(path).get("managed", False):
        raise PermissionError(f"Cannot edit managed standard '{standard_id}'")
    io.write(path, {**data, "id": standard_id, "type": _TYPE_CUSTOM, "managed": False})
    return build_detail(io.read(path))


def delete(standard_id: str, evaluators_dir: Path, compiled_dir: Path,
           io: JsonIO, is_builtin: Callable[[str], bool]) -> None:
    """Delete a custom standard. Raises for built-in or managed standards."""
    path = evaluators_dir / f"{standard_id}.json"
    if not path.is_file():
        if (compiled_dir / f"{standard_id}.json").is_file() or is_builtin(standard_id):
            raise PermissionError(f"Cannot delete built-in standard '{standard_id}'")
        raise FileNotFoundError(f"Standard not found: {standard_id}")
    if io.read(path).get("managed", False):
        raise PermissionError(f"Cannot delete managed standard '{standard_id}'")
    path.unlink()


def duplicate(standard_id: str, new_id: str, source_detail: StandardDetail,
              evaluators_dir: Path, io: JsonIO) -> StandardDetail:
    """Duplicate an existing standard under *new_id* as a custom copy."""
    _validate_id(new_id)
    new_path = evaluators_dir / f"{new_id}.json"
    if new_path.exists():
        raise ValueError(f"Standard '{new_id}' already exists")
    evaluators_dir.mkdir(parents=True, exist_ok=True)
    s = source_detail
    payload = {"id": new_id, "name": s.name, "description": s.description,
               "weight": s.weight, "source": s.source, "principles": s.principles,
               **_CUSTOM_DEFAULTS}
    io.write(new_path, payload)
    return build_detail(io.read(new_path))


def import_from_file(data: dict, force: bool, evaluators_dir: Path, io: JsonIO) -> dict:
    """Import an evaluator from parsed file data."""
    validation = validate_import(data)
    if not validation["valid"]:
        raise ValueError("; ".join(validation["errors"]))
    cleaned = validation["data"]
    warnings = scan_injection(cleaned)
    standard_id = cleaned["id"]
    path = evaluators_dir / f"{standard_id}.json"
    if path.is_file() and not force:
        existing = io.read(path)
        p, r = count_principles_and_requirements(existing)
        return {"status": "conflict", "detail": None,
                "existing": build_custom_meta(existing, p, r), "warnings": warnings}
    if path.is_file() and force and io.read(path).get("managed", False):
        raise PermissionError(f"Cannot overwrite managed standard '{standard_id}'")
    evaluators_dir.mkdir(parents=True, exist_ok=True)
    io.write(path, {**cleaned, **_CUSTOM_DEFAULTS})
    return {"status": "imported", "detail": build_detail(io.read(path)),
            "existing": None, "warnings": warnings}
