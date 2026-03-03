from __future__ import annotations

import json
from pathlib import Path

import pytest

from codecompass.config.scaffold import scaffold_plugin, RUNTIME_PRESETS
from codecompass.v2.engine.schema_validator import validate_plugin_dir


@pytest.mark.parametrize("runtime", list(RUNTIME_PRESETS.keys()))
def test_scaffold_creates_all_files(tmp_path, runtime):
    plugin_dir = scaffold_plugin(runtime, tmp_path)
    assert (plugin_dir / "plugin.json").exists()
    assert (plugin_dir / "dimensions.json").exists()
    assert (plugin_dir / "detectors.json").exists()
    assert (plugin_dir / "scan_rules.ini").exists()
    assert (plugin_dir / "knowledge" / "practices.json").exists()
    assert (plugin_dir / "knowledge" / "analysis.md").exists()


@pytest.mark.parametrize("runtime", list(RUNTIME_PRESETS.keys()))
def test_scaffold_passes_schema_validation(tmp_path, runtime):
    plugin_dir = scaffold_plugin(runtime, tmp_path)
    errors = validate_plugin_dir(plugin_dir)
    assert errors == {}, f"Schema errors for {runtime}: {errors}"


def test_scaffold_raises_on_existing_dir(tmp_path):
    scaffold_plugin("kotlin", tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        scaffold_plugin("kotlin", tmp_path)


def test_scaffold_raises_on_unknown_runtime(tmp_path):
    with pytest.raises(ValueError, match="Unknown runtime"):
        scaffold_plugin("fortran", tmp_path)


def test_scaffold_plugin_json_has_correct_id(tmp_path):
    plugin_dir = scaffold_plugin("python", tmp_path)
    data = json.loads((plugin_dir / "plugin.json").read_text())
    assert data["id"] == "python"
    assert data["detects"]["extensions"] == [".py"]
