from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.engine.plugin_loader import load_plugin
from quodeq.engine.schema_validator import validate_plugin_dir

from quodeq.config.paths import default_paths


@pytest.fixture()
def plugin_dir() -> Path:
    path = default_paths().evaluators_dir / "kotlin"
    if not path.exists():
        pytest.skip("kotlin evaluator not installed")
    return path


def test_plugin_loads(plugin_dir: Path) -> None:
    data = load_plugin(plugin_dir)
    assert data["id"] == "kotlin"


def test_plugin_passes_validation(plugin_dir: Path) -> None:
    errors = validate_plugin_dir(plugin_dir)
    assert errors == {}, f"Validation errors: {errors}"
