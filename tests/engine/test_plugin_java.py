from __future__ import annotations

from pathlib import Path

from quodeq.engine.plugin_loader import load_plugin
from quodeq.engine.schema_validator import validate_plugin_dir

PLUGIN_DIR = Path(__file__).parent.parent.parent / "evaluators" / "java"


def test_plugin_loads():
    data = load_plugin(PLUGIN_DIR)
    assert data["id"] == "java"


def test_plugin_passes_validation():
    errors = validate_plugin_dir(PLUGIN_DIR)
    assert errors == {}, f"Validation errors: {errors}"
