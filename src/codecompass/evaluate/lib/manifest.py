from __future__ import annotations

from pathlib import Path
import json
from typing import Any

MANIFEST_FILENAME = ".codecompass.json"

_manifest_cache: dict[str, dict[str, Any]] = {}


def manifest_exists(work_dir: str) -> bool:
    return Path(work_dir, MANIFEST_FILENAME).is_file()


def manifest_path(work_dir: str) -> str:
    return str(Path(work_dir, MANIFEST_FILENAME))


def _load_manifest(manifest: str | Path) -> dict[str, Any]:
    key = str(Path(manifest).resolve())
    if key not in _manifest_cache:
        _manifest_cache[key] = json.loads(Path(manifest).read_text())
    return _manifest_cache[key]


def parse_manifest_project_name(manifest: str | Path) -> str:
    data = _load_manifest(manifest)
    return str(data.get("project", {}).get("name", "") or "")


def parse_manifest_target_count(manifest: str | Path) -> int:
    data = _load_manifest(manifest)
    targets = data.get("targets", [])
    return len(targets)


def parse_manifest_target_core_fields(manifest: str | Path, index: int) -> tuple[str, str, str]:
    data = _load_manifest(manifest)
    targets = data.get("targets", [])
    target = targets[index] if index < len(targets) else {}
    name = str(target.get("name", "") or "")
    path = str(target.get("path", "") or "")
    discipline = str(target.get("discipline", "") or "")
    return name, path, discipline


def parse_manifest_target_field(manifest: str | Path, index: int, field: str) -> str:
    data = _load_manifest(manifest)
    targets = data.get("targets", [])
    target = targets[index] if index < len(targets) else {}
    return str(target.get(field, "") or "")


def parse_manifest_target_dimensions(manifest: str | Path, index: int) -> list[str]:
    data = _load_manifest(manifest)
    targets = data.get("targets", [])
    target = targets[index] if index < len(targets) else {}
    dimensions = target.get("dimensions")
    if isinstance(dimensions, str):
        return [dimensions]
    if isinstance(dimensions, list):
        return [str(item) for item in dimensions]
    return ["all"]


def validate_manifest(manifest: str | Path) -> list[str]:
    errors: list[str] = []
    path = Path(manifest)

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return [f"Invalid JSON in {path}"]

    if not data.get("version"):
        errors.append("Missing 'version' field in manifest")

    targets = data.get("targets", [])
    if len(targets) == 0:
        errors.append("Manifest has no targets")
        return errors

    for idx, target in enumerate(targets):
        name = target.get("name") or ""
        path_value = target.get("path") or ""
        discipline = target.get("discipline") or ""
        if not name:
            errors.append(f"Target {idx} missing 'name'")
        if not path_value:
            errors.append(f"Target '{name}' missing 'path'")
        if not discipline:
            errors.append(f"Target '{name}' missing 'discipline'")

    return errors
