from __future__ import annotations

from pathlib import Path

from codecompass.engine.plugin_loader import load_plugin
from codecompass.engine.schema_validator import validate_plugin_dir

PLUGIN_DIR = Path(__file__).parent.parent.parent / "evaluators" / "mobile_ios"


def test_plugin_loads():
    data = load_plugin(PLUGIN_DIR)
    assert data["id"] == "mobile_ios"


def test_plugin_passes_validation():
    errors = validate_plugin_dir(PLUGIN_DIR)
    assert errors == {}, f"Validation errors: {errors}"
