"""I/O helpers and data-conversion utilities for the standards service."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.types.standard import StandardDetail, StandardMeta
logger = logging.getLogger(__name__)

_TYPE_CUSTOM = "custom"
_TYPE_BUILTIN = "builtin"


def _require_id(data: dict, source: str) -> str:
    """Return data['id'], raising ValueError with context if missing/empty.

    Standards are user-uploaded JSON; surfacing the bad payload as a
    ValueError lets API routes return a 400 instead of a 500 KeyError.
    """
    sid = data.get("id")
    if not isinstance(sid, str) or not sid:
        raise ValueError(f"{source} missing required 'id' field")
    return sid


def default_read_json(path: Path) -> dict:
    """Read and parse a JSON file from disk."""
    return json.loads(path.read_text())


def default_write_json(path: Path, data: dict) -> None:
    """Serialize *data* as pretty-printed JSON and write it to *path*."""
    path.write_text(json.dumps(data, indent=2))


def count_principles_and_requirements(data: dict) -> tuple[int, int]:
    """Return (principle_count, requirement_count) from a standard's JSON."""
    principles = data.get("principles", [])
    return len(principles), sum(len(p.get("requirements", [])) for p in principles)


def build_detail(data: dict, *, type_default: str = _TYPE_CUSTOM) -> StandardDetail:
    """Construct a StandardDetail from a raw JSON dict."""
    sid = _require_id(data, "standard")
    return StandardDetail(
        id=sid, name=data.get("name", sid),
        description=data.get("description", ""),
        weight=data.get("weight", 1.0), source=data.get("source", ""),
        type=data.get("type", type_default), managed=data.get("managed", False),
        origin=data.get("origin"), origin_hash=data.get("origin_hash"),
        principles=data.get("principles", []),
    )


def build_builtin_detail(data: dict, standard_id: str, weight: float) -> StandardDetail:
    source = data.get("source", "") or ", ".join(data.get("sources", []))
    description = data.get("description") or f"{data.get('name', standard_id)} standard"
    return StandardDetail(
        id=standard_id, name=data.get("name", standard_id),
        description=description,
        weight=weight, source=source,
        type=data.get("type", _TYPE_BUILTIN), managed=True,
        origin=None, origin_hash=None, principles=data.get("principles", []),
    )


def build_custom_meta(data: dict, p_count: int, r_count: int) -> StandardMeta:
    """Build a StandardMeta for a user-created custom standard."""
    sid = _require_id(data, "custom standard")
    return StandardMeta(
        id=sid, name=data.get("name", sid),
        description=data.get("description", ""),
        weight=data.get("weight", 1.0), source=data.get("source", ""),
        type=data.get("type", _TYPE_CUSTOM), managed=data.get("managed", False),
        origin=data.get("origin"), origin_hash=data.get("origin_hash"),
        principle_count=p_count, requirement_count=r_count,
    )


def build_builtin_meta(
    dim: dict, p_count: int, r_count: int, description: str = "",
) -> StandardMeta:
    """Build a StandardMeta for a built-in dimension.

    *description* is the description loaded from the compiled standard file,
    when available. Falls back to a generic "{source} standard" label so
    older compiled files without the field keep their historical meta text.
    """
    did = _require_id(dim, "built-in dimension")
    final_description = description or f'{dim.get("source", "Built-in")} standard'
    return StandardMeta(
        id=did, name=dim.get("iso_25010") or dim.get("name", did),
        description=final_description,
        weight=dim.get("weight", 1.0), source=dim.get("source", ""),
        type=dim.get("type", _TYPE_BUILTIN), managed=True,
        origin=None, origin_hash=None,
        principle_count=p_count, requirement_count=r_count,
    )


def get_builtin_weight(dimensions_data: dict, dimension_id: str) -> float:
    """Return the weight of a built-in dimension, defaulting to 1.0."""
    for dim in dimensions_data.get("applies", []):
        if dim["id"] == dimension_id:
            return dim.get("weight", 1.0)
    return 1.0


def is_builtin_id(dimensions_data: dict, standard_id: str) -> bool:
    """Check whether *standard_id* corresponds to a built-in dimension."""
    return any(dim["id"] == standard_id for dim in dimensions_data.get("applies", []))


def load_cwe_entries(entries: list) -> list[dict]:
    """Normalize raw CWE entries into a list of slim dicts.

    Entries lacking ``id`` or ``name`` are skipped rather than raising
    KeyError, since the CWE corpus is third-party data and a single
    malformed row should not abort the whole load.
    """
    out: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        ename = e.get("name")
        if eid is None or ename is None:
            continue
        out.append({
            "id": eid, "name": ename,
            "abstraction": e.get("abstraction", ""),
            "dimensions": e.get("dimensions", []),
        })
    return out
