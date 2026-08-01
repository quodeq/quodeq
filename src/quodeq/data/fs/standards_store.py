"""Custom-standard file mechanics for the evaluators directory.

services/_standards_crud composed paths, checked existence, mkdir'd and
unlinked inline; services/standards_library wrote payloads with
write_text. The path/file mechanics live here; validation and permission
decisions (managed/builtin/collision rules) stay in the services, and the
CRUD service keeps its injected JsonIO for the payload contents.
"""
from __future__ import annotations

import json
from pathlib import Path


def standard_path(evaluators_dir: Path, standard_id: str) -> Path:
    """The on-disk path for *standard_id* in *evaluators_dir*."""
    return evaluators_dir / f"{standard_id}.json"


def standard_exists(evaluators_dir: Path, standard_id: str) -> bool:
    """True when the standard's file exists."""
    return standard_path(evaluators_dir, standard_id).is_file()


def compiled_exists(compiled_dir: Path, standard_id: str) -> bool:
    """True when a compiled (built-in) standard file exists."""
    return (compiled_dir / f"{standard_id}.json").is_file()


def ensure_evaluators_dir(evaluators_dir: Path) -> None:
    """Create the evaluators directory (and parents) if absent."""
    evaluators_dir.mkdir(parents=True, exist_ok=True)


def remove_standard(evaluators_dir: Path, standard_id: str) -> None:
    """Delete the standard's file. Raises FileNotFoundError when absent."""
    standard_path(evaluators_dir, standard_id).unlink()


def resolve_jailed_standard_path(evaluators_dir: Path, standard_id: str) -> Path:
    """Resolved path for *standard_id*, guaranteed inside *evaluators_dir*.

    Raises ValueError when the id would escape the directory (defense in
    depth behind the services' own id validation).
    """
    dest = (evaluators_dir / f"{standard_id}.json").resolve()
    if not dest.is_relative_to(evaluators_dir.resolve()):
        raise ValueError(f"Invalid standard ID: {standard_id}")
    return dest


def read_standard_payload(path: Path) -> dict | None:
    """Parsed standard JSON at *path*, or None when the file is absent."""
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_standard_payload(path: Path, data: dict) -> None:
    """Write a standard payload, creating the parent directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)
    path.write_text(payload, encoding="utf-8")
