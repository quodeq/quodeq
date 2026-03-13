from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine.plugin_loader import load_plugin, load_plugin_full
from quodeq.engine.schema_validator import validate_plugin_dir

from quodeq.config.paths import default_paths

PLUGIN_DIR = default_paths().evaluators_dir / "bash"


def test_plugin_loads():
    data = load_plugin(PLUGIN_DIR)
    assert data["id"] == "bash"


def test_plugin_passes_validation():
    errors = validate_plugin_dir(PLUGIN_DIR)
    assert errors == {}, f"Validation errors: {errors}"


def test_plugin_load_missing_dir(tmp_path):
    with pytest.raises((FileNotFoundError, OSError)):
        load_plugin(tmp_path / "nonexistent")


def test_plugin_load_full_invalid_json(tmp_path):
    (tmp_path / "plugin.json").write_text("{bad json")
    with pytest.raises((json.JSONDecodeError, ValueError)):
        load_plugin_full(tmp_path)
