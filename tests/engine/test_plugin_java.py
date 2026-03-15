from __future__ import annotations

import json

import pytest

from quodeq.engine.plugin_loader import load_plugin, load_plugin_full
from quodeq.engine.schema_validator import validate_plugin_dir

from quodeq.config.paths import default_paths


@pytest.fixture(params=["java", "python"], ids=["java", "python"])
def plugin_dir(request):
    return default_paths().evaluators_dir / request.param


def test_plugin_loads(plugin_dir):
    data = load_plugin(plugin_dir)
    assert data["id"] == plugin_dir.name


def test_plugin_passes_validation(plugin_dir):
    errors = validate_plugin_dir(plugin_dir)
    assert errors == {}, f"Validation errors: {errors}"


def test_plugin_load_missing_dir(tmp_path):
    with pytest.raises((FileNotFoundError, OSError, ValueError)):
        load_plugin(tmp_path / "nonexistent")


def test_plugin_load_invalid_json(tmp_path):
    (tmp_path / "plugin.json").write_text("{bad json")
    with pytest.raises((json.JSONDecodeError, ValueError)):
        load_plugin_full(tmp_path)
