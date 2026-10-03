"""Build admission's ``StandardIndex`` from the standard files on disk.

The same precedence as every reader: a custom evaluator that defines the
dimension wins, otherwise the compiled built-in standard. A missing,
unreadable or malformed file yields no index, which admission reports as
``no_standard`` instead of guessing.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from quodeq.core.admission import StandardCatalog, StandardIndex

_logger = logging.getLogger(__name__)


def _read(directory: Path | None, dimension: str) -> dict | None:
    if directory is None:
        return None
    path = directory / f"{dimension}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _logger.warning("Standard %s is unreadable: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def _index_of(dimension: str, data: dict) -> StandardIndex | None:
    req_to_principle: dict[str, str] = {}
    req_refs: dict[str, tuple[dict, ...]] = {}
    for principle in data.get("principles") or []:
        if not isinstance(principle, dict) or not principle.get("name"):
            continue
        for req in principle.get("requirements") or []:
            if not isinstance(req, dict) or not req.get("id"):
                continue
            req_to_principle[req["id"]] = principle["name"]
            refs = req.get("refs") or []
            req_refs[req["id"]] = tuple(r for r in refs if isinstance(r, dict))
    if not req_to_principle:
        return None
    return StandardIndex(dimension, req_to_principle, req_refs)


def load_standard_index(
    dimension: str, *, evaluators_dir: Path | None, compiled_dir: Path | None,
) -> StandardIndex | None:
    """The index of *dimension*'s standard, or None when neither source defines it."""
    for directory in (evaluators_dir, compiled_dir):
        data = _read(directory, dimension)
        if data is not None and (index := _index_of(dimension, data)) is not None:
            return index
    return None


def load_standard_catalog(
    dimensions: Iterable[str], *, evaluators_dir: Path | None, compiled_dir: Path | None,
) -> StandardCatalog:
    """A catalog of every *dimensions* entry that has a loadable standard."""
    indexes = (
        load_standard_index(d, evaluators_dir=evaluators_dir, compiled_dir=compiled_dir)
        for d in dimensions
    )
    return StandardCatalog.of(i for i in indexes if i is not None)
