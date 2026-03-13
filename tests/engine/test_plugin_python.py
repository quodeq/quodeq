from __future__ import annotations

from pathlib import Path

from quodeq.engine.plugin_loader import load_plugin
from quodeq.engine.schema_validator import validate_plugin_dir

from quodeq.config.paths import default_paths

PLUGIN_DIR = default_paths().evaluators_dir / "python"


def test_plugin_loads():
    data = load_plugin(PLUGIN_DIR)
    assert data["id"] == "python"


def test_plugin_passes_validation():
    errors = validate_plugin_dir(PLUGIN_DIR)
    assert errors == {}, f"Validation errors: {errors}"
