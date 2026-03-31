"""Re-export for backward compatibility — moved to quodeq.core.standards.loader.

This engine-layer module supplies the default ``paths_fn`` so that callers
do not need to know about ``config.paths`` themselves.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.core.standards.loader import (
    load_dimension as _load_dimension,
    load_asvs_l1 as _load_asvs_l1,
    load_cisq as _load_cisq,
)


def load_dimension(dimension_id: str, standards_dir: Path | None = None) -> dict:
    return _load_dimension(dimension_id, standards_dir, paths_fn=default_paths)


def load_asvs_l1(standards_dir: Path | None = None) -> dict:
    return _load_asvs_l1(standards_dir, paths_fn=default_paths)


def load_cisq(characteristic: str, standards_dir: Path | None = None) -> dict:
    return _load_cisq(characteristic, standards_dir, paths_fn=default_paths)
