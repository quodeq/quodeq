from __future__ import annotations

import json
from pathlib import Path

from codecompass.v2.engine.plugin_loader import load_plugin
from codecompass.v2.engine.schema_validator import validate_plugin_dir

PLUGIN_DIR = Path(__file__).parent.parent.parent / "v2" / "evaluators" / "kotlin"


def test_plugin_loads():
    data = load_plugin(PLUGIN_DIR)
    assert data["id"] == "kotlin"


def test_plugin_has_knowledge():
    practices = json.loads((PLUGIN_DIR / "knowledge" / "practices.json").read_text())
    assert len(practices["practices"]) >= 3


def test_plugin_passes_validation():
    errors = validate_plugin_dir(PLUGIN_DIR)
    assert errors == {}, f"Validation errors: {errors}"
