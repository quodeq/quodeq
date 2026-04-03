"""I/O helpers and data-conversion utilities for the standards service."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.types.standard import StandardDetail, StandardMeta
logger = logging.getLogger(__name__)

_TYPE_CUSTOM = "custom"
_TYPE_BUILTIN = "builtin"


def default_read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def default_write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def count_principles_and_requirements(data: dict) -> tuple[int, int]:
    """Return (principle_count, requirement_count) from a standard's JSON."""
    principles = data.get("principles", [])
    return len(principles), sum(len(p.get("requirements", [])) for p in principles)


def build_detail(data: dict, *, type_default: str = _TYPE_CUSTOM) -> StandardDetail:
    return StandardDetail(
        id=data["id"], name=data.get("name", data["id"]),
        description=data.get("description", ""),
        weight=data.get("weight", 1.0), source=data.get("source", ""),
        type=data.get("type", type_default), managed=data.get("managed", False),
        origin=data.get("origin"), origin_hash=data.get("origin_hash"),
        principles=data.get("principles", []),
    )


def build_builtin_detail(data: dict, standard_id: str, weight: float) -> StandardDetail:
    source = data.get("source", "") or ", ".join(data.get("sources", []))
    return StandardDetail(
        id=standard_id, name=data.get("name", standard_id),
        description=f"{data.get('name', standard_id)} standard",
        weight=weight, source=source,
        type=data.get("type", _TYPE_BUILTIN), managed=True,
        origin=None, origin_hash=None, principles=data.get("principles", []),
    )


def build_custom_meta(data: dict, p_count: int, r_count: int) -> StandardMeta:
    return StandardMeta(
        id=data["id"], name=data.get("name", data["id"]),
        description=data.get("description", ""),
        weight=data.get("weight", 1.0), source=data.get("source", ""),
        type=data.get("type", _TYPE_CUSTOM), managed=data.get("managed", False),
        origin=data.get("origin"), origin_hash=data.get("origin_hash"),
        principle_count=p_count, requirement_count=r_count,
    )


def build_builtin_meta(dim: dict, p_count: int, r_count: int) -> StandardMeta:
    return StandardMeta(
        id=dim["id"], name=dim.get("iso_25010") or dim.get("name", dim["id"]),
        description=f'{dim.get("source", "Built-in")} standard',
        weight=dim.get("weight", 1.0), source=dim.get("source", ""),
        type=dim.get("type", _TYPE_BUILTIN), managed=True,
        origin=None, origin_hash=None,
        principle_count=p_count, requirement_count=r_count,
    )


def get_builtin_weight(dimensions_data: dict, dimension_id: str) -> float:
    for dim in dimensions_data.get("applies", []):
        if dim["id"] == dimension_id:
            return dim.get("weight", 1.0)
    return 1.0


def is_builtin_id(dimensions_data: dict, standard_id: str) -> bool:
    return any(dim["id"] == standard_id for dim in dimensions_data.get("applies", []))


def load_cwe_entries(entries: list) -> list[dict]:
    return [{"id": e["id"], "name": e["name"],
             "abstraction": e.get("abstraction", ""), "dimensions": e.get("dimensions", [])}
            for e in entries]
