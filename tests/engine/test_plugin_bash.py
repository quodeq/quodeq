from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine.plugin_loader import load_plugin, load_plugin_full
from quodeq.engine.schema_validator import validate_plugin_dir

from quodeq.config.paths import default_paths


@pytest.fixture()
def plugin_dir() -> Path:
    return default_paths().evaluators_dir / "bash"


def test_plugin_loads(plugin_dir: Path) -> None:
    data = load_plugin(plugin_dir)
    assert data["id"] == "bash"


def test_plugin_passes_validation(plugin_dir: Path) -> None:
    errors = validate_plugin_dir(plugin_dir)
    assert errors == {}, f"Validation errors: {errors}"


def test_plugin_load_missing_dir(tmp_path: Path) -> None:
    with pytest.raises((FileNotFoundError, OSError, ValueError)):
        load_plugin(tmp_path / "nonexistent")


def test_plugin_load_full_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "plugin.json").write_text("{bad json")
    with pytest.raises((json.JSONDecodeError, ValueError)):
        load_plugin_full(tmp_path)
