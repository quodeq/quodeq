import json
from pathlib import Path

from codecompass.evaluate.lib.manifest import (
    MANIFEST_FILENAME,
    manifest_exists,
    manifest_path,
    parse_manifest_project_name,
    parse_manifest_target_count,
    parse_manifest_target_core_fields,
    parse_manifest_target_dimensions,
    validate_manifest,
)


def _write_manifest(path: Path, payload: dict) -> Path:
    file_path = path / MANIFEST_FILENAME
    file_path.write_text(json.dumps(payload))
    return file_path


def test_manifest_exists(tmp_path: Path):
    payload = {"version": 1, "project": {"name": "demo"}, "targets": []}
    _write_manifest(tmp_path, payload)
    assert manifest_exists(str(tmp_path))
    assert manifest_path(str(tmp_path)).endswith(MANIFEST_FILENAME)


def test_manifest_parsing_fields(tmp_path: Path):
    payload = {
        "version": 1,
        "project": {"name": "demo"},
        "targets": [
            {"name": "api", "path": "services/api", "discipline": "backend", "dimensions": "all"},
            {"name": "web", "path": "apps/web", "discipline": "frontend", "dimensions": ["mnt"]},
        ],
    }
    manifest = _write_manifest(tmp_path, payload)

    assert parse_manifest_project_name(manifest) == "demo"
    assert parse_manifest_target_count(manifest) == 2
    assert parse_manifest_target_core_fields(manifest, 0) == ("api", "services/api", "backend")
    assert parse_manifest_target_dimensions(manifest, 0) == ["all"]
    assert parse_manifest_target_dimensions(manifest, 1) == ["mnt"]


def test_validate_manifest_reports_errors(tmp_path: Path):
    payload = {"project": {"name": "demo"}, "targets": []}
    manifest = _write_manifest(tmp_path, payload)

    errors = validate_manifest(manifest)
    assert "Missing 'version' field in manifest" in errors
    assert "Manifest has no targets" in errors
