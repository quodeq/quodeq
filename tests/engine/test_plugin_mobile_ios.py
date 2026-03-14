from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.engine.plugin_loader import load_plugin
from quodeq.engine.schema_validator import validate_plugin_dir
from quodeq.config.paths import default_paths


@pytest.fixture
def plugin_dir():
    """Resolve the mobile_ios plugin directory, skipping if absent."""
    d = default_paths().evaluators_dir / "mobile_ios"
    if not d.exists():
        pytest.skip(f"Plugin directory not found: {d}")
    return d


def test_plugin_loads(plugin_dir):
    data = load_plugin(plugin_dir)
    assert data["id"] == "mobile_ios"


def test_plugin_passes_validation(plugin_dir):
    errors = validate_plugin_dir(plugin_dir)
    assert errors == {}, f"Validation errors: {errors}"
