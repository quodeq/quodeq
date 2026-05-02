"""Query operations for listing and retrieving standards."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from quodeq.core.types.standard import StandardDetail, StandardMeta
from quodeq.services._standards_io import (
    build_builtin_detail, build_builtin_meta, build_custom_meta, build_detail,
    count_principles_and_requirements, get_builtin_weight, is_builtin_id,
    load_cwe_entries,
)
from quodeq.shared.validation import validate_path_segment

logger = logging.getLogger(__name__)


def list_builtin(dimensions_file: Path, compiled_dir: Path,
                 read_json: Callable) -> list[StandardMeta]:
    """Return metadata for all built-in standards."""
    try:
        data = read_json(dimensions_file)
    except (OSError, ValueError) as exc:
        logger.warning("Cannot read dimensions file: %s", exc)
        return []
    return [build_builtin_meta(dim, *_count_compiled(dim["id"], compiled_dir, read_json))
            for dim in data.get("applies", [])]


def _count_compiled(dimension_id: str, compiled_dir: Path,
                    read_json: Callable) -> tuple[int, int]:
    path = compiled_dir / f"{dimension_id}.json"
    if not path.is_file():
        return 0, 0
    try:
        return count_principles_and_requirements(read_json(path))
    except (OSError, ValueError):
        return 0, 0


def list_custom(evaluators_dir: Path, read_json: Callable) -> list[StandardMeta]:
    """Return metadata for all custom evaluators."""
    if not evaluators_dir.is_dir():
        return []
    out: list[StandardMeta] = []
    for path in sorted(evaluators_dir.glob("*.json")):
        try:
            data = read_json(path)
            out.append(build_custom_meta(data, *count_principles_and_requirements(data)))
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Skipping invalid evaluator %s: %s", path.name, exc)
    return out


def get_standard(standard_id: str, evaluators_dir: Path, compiled_dir: Path,
                 dimensions_file: Path, read_json: Callable) -> StandardDetail:
    """Return full detail for a single standard, checking custom then built-in.

    Validates *standard_id* up-front so a path-traversal segment ('../foo')
    cannot reach the filesystem join below.
    """
    validate_path_segment(standard_id)
    custom_path = evaluators_dir / f"{standard_id}.json"
    if custom_path.is_file():
        return build_detail(read_json(custom_path))
    compiled_path = compiled_dir / f"{standard_id}.json"
    if compiled_path.is_file():
        try:
            weight = get_builtin_weight(read_json(dimensions_file), standard_id)
        except (OSError, ValueError):
            weight = 1.0
        return build_builtin_detail(read_json(compiled_path), standard_id, weight)
    raise FileNotFoundError(f"Standard not found: {standard_id}")


def check_builtin_id(standard_id: str, dimensions_file: Path,
                     read_json: Callable) -> bool:
    """Return True if *standard_id* is a built-in dimension."""
    try:
        return is_builtin_id(read_json(dimensions_file), standard_id)
    except (OSError, ValueError):
        return False


def load_cwe_list(compiled_dir: Path, read_json: Callable) -> list[dict]:
    """Load the CWE reference list from the compiled standards directory."""
    cwe_path = compiled_dir.parent / "cwe" / "audit.json"
    if not cwe_path.is_file():
        return []
    try:
        return load_cwe_entries(read_json(cwe_path))
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Cannot read CWE list: %s", exc)
        return []
