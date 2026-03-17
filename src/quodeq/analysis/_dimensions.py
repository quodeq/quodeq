"""Dimension configuration types and loader for universal analysis."""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from quodeq.analysis.plugins.schema_validator import validate_dimensions
from quodeq.shared.utils import read_json


class DimensionEntry(TypedDict, total=False):
    """Shape of one entry in dimensions.json ``applies`` list."""
    id: str
    weight: float
    iso_25010: str
    source: str


class DimensionsConfig(TypedDict, total=False):
    """Shape of a validated dimensions.json file."""
    applies: list[DimensionEntry]
    excludes: list[str]


def load_universal_dimensions(dimensions_file: Path) -> DimensionsConfig:
    """Load and validate the universal dimensions.json config.

    Returns the parsed dimensions dict.
    Raises ValueError on validation failure.
    """
    dims_data = read_json(dimensions_file)
    errors = validate_dimensions(dims_data)
    if errors:
        raise ValueError(f"dimensions.json: {'; '.join(errors)}")
    return dims_data
