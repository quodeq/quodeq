"""Tests for universal dimensions.json loading."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.runner import load_universal_dimensions
from quodeq.config.paths import default_paths


@pytest.fixture()
def dims_file() -> Path:
    path = default_paths().dimensions_file
    if not path.exists():
        pytest.skip("universal dimensions.json not installed")
    return path


def test_loads_universal_dimensions(dims_file: Path) -> None:
    data = load_universal_dimensions(dims_file)
    assert "applies" in data
    dims = [d["id"] for d in data["applies"]]
    assert "security" in dims
    assert "reliability" in dims
    assert "maintainability" in dims


def test_all_dimensions_have_weight(dims_file: Path) -> None:
    data = load_universal_dimensions(dims_file)
    for dim in data["applies"]:
        assert "weight" in dim
        assert isinstance(dim["weight"], (int, float))


def test_invalid_dimensions_raises(tmp_path: Path) -> None:
    bad_file = tmp_path / "dimensions.json"
    bad_file.write_text(json.dumps({"wrong": "schema"}))
    with pytest.raises(ValueError):
        load_universal_dimensions(bad_file)
