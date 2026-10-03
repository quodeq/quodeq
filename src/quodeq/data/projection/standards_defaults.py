"""The install's standards directories, and the warning for findings they cannot place."""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.config.paths import default_paths

_logger = logging.getLogger(__name__)


def _existing(path: Path | None) -> Path | None:
    return path if path is not None and path.is_dir() else None


def default_standards_dirs() -> tuple[Path | None, Path | None]:
    """(compiled_dir, evaluators_dir) of this install; None when absent."""
    paths = default_paths()
    compiled = paths.standards_dir / "compiled" if paths.standards_dir else None
    return _existing(compiled), _existing(paths.evaluators_dir)


def warn_unmapped(unmapped_by_dimension: dict[str, int]) -> None:
    """Say, once per dimension, how many findings could not be placed."""
    for dimension, count in sorted(unmapped_by_dimension.items()):
        _logger.warning(
            "%d %s finding(s) have no principle and their requirement code is not "
            "in the dimension's standard; left out of the grade", count, dimension,
        )
