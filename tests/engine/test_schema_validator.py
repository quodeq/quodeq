from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine.schema_validator import (
    validate_plugin,
    validate_dimensions,
    validate_plugin_dir,
)


# ── plugin.json ───────────────────────────────────────────────────────

def _valid_plugin():
    return {
        "id": "typescript",
        "name": "TypeScript / Node.js",
        "version": "1.0.0",
        "engine_version": "==0.3.0",
        "detects": {
            "extensions": [".ts", ".tsx"],
            "config_files": ["tsconfig.json"],
        },
    }


def test_valid_plugin():
    assert validate_plugin(_valid_plugin()) == []


def test_plugin_missing_id():
    data = _valid_plugin()
    del data["id"]
    errors = validate_plugin(data)
    assert any("id" in e for e in errors)


def test_plugin_bad_id_pattern():
    data = _valid_plugin()
    data["id"] = "TypeScript"  # uppercase not allowed
    errors = validate_plugin(data)
    assert errors


def test_plugin_missing_extensions():
    data = _valid_plugin()
    data["detects"] = {"config_files": ["x"]}
    errors = validate_plugin(data)
    assert any("extensions" in e for e in errors)


def test_plugin_empty_extensions():
    data = _valid_plugin()
    data["detects"]["extensions"] = []
    assert validate_plugin(data) != []


# ── dimensions.json ───────────────────────────────────────────────────

def _valid_dimensions():
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
        ],
        "excludes": ["usability"],
    }


def test_valid_dimensions():
    assert validate_dimensions(_valid_dimensions()) == []


def test_dimensions_without_optional_fields():
    data = {"applies": [{"id": "maintainability", "weight": 1.0}]}
    assert validate_dimensions(data) == []


def test_dimensions_missing_applies():
    assert validate_dimensions({}) != []


def test_dimensions_missing_weight():
    data = {"applies": [{"id": "security"}]}
    assert validate_dimensions(data) != []


# ── validate_plugin_dir ───────────────────────────────────────────────

def test_validate_real_typescript_plugin():
    from quodeq.config.paths import default_paths
    ts_dir = default_paths().evaluators_dir / "typescript"
    if not ts_dir.exists():
        pytest.skip("TypeScript plugin not available")
    errors = validate_plugin_dir(ts_dir)
    assert errors == {}, f"Validation errors: {errors}"


def test_validate_plugin_dir_missing_files(tmp_path):
    errors = validate_plugin_dir(tmp_path)
    assert "plugin.json" in errors
    assert "dimensions.json" in errors


def test_validate_plugin_dir_with_invalid_plugin(tmp_path):
    (tmp_path / "plugin.json").write_text(json.dumps({"id": "BAD"}))
    (tmp_path / "dimensions.json").write_text(json.dumps({"applies": [{"id": "x", "weight": 1}]}))
    errors = validate_plugin_dir(tmp_path)
    assert "plugin.json" in errors
