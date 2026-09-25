"""Template section renderers for analysis prompts."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from quodeq.core.standards.overrides import resolve_requirement_text
from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)

_NO_STANDARDS_FOR_DIM = "_No compiled standards for this dimension._"
_FIELD_ID = "id"  # the compiled-standards field name _require_field looks up


def _require_field(entry: dict, field: str, kind: str) -> object:
    """``entry[field]``, or a ValueError naming the malformed *kind* of entry.

    Compiled standards are the contract the prompt is built from: a
    principle with no name, a requirement with no id or a dimension with no
    id cannot be rendered, and failing here names the offending entry.
    """
    value = entry.get(field)
    if value is None:
        raise ValueError(
            f"Malformed standards file: a {kind} is missing required {field!r}: {entry!r}"
        )
    return value


def _principles_with_requirements(data: dict) -> Iterator[tuple[dict, list[dict]]]:
    """Yield each principle that has requirements, with its requirement list."""
    for principle in data.get("principles", []):
        reqs = principle.get("requirements", [])
        if reqs:
            yield principle, reqs


def _resolved_requirements(
    reqs: list[dict], overrides: dict[str, dict] | None,
) -> Iterator[tuple[dict, object, str]]:
    """Yield ``(req, id, text)`` per requirement, with the project's threshold overrides applied."""
    for req in reqs:
        req_id = _require_field(req, _FIELD_ID, "requirement")
        yield req, req_id, resolve_requirement_text(req, (overrides or {}).get(req_id))


def load_dimension_data(
    compiled_dir: Path,
    dimension: str,
    evaluators_dir: Path | None = None,
) -> dict | None:
    """Load compiled standards JSON for a dimension, or None on error.

    Falls back to *evaluators_dir* when the compiled file does not exist and
    *evaluators_dir* is provided (supports custom / user-supplied standards).
    """
    path = compiled_dir / f"{dimension}.json"
    if not path.is_file() and evaluators_dir is not None:
        path = evaluators_dir / f"{dimension}.json"
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except (OSError, ValueError) as exc:
        _logger.warning(
            "Failed to load dimension %s: %s. "
            "Check that the compiled standards JSON file exists and is valid.",
            dimension, exc,
        )
        return None


def render_compiled_standards(
    compiled_dir: Path,
    dimension: str,
    evaluators_dir: Path | None = None,
    overrides: dict[str, dict] | None = None,
) -> str:
    """Render compiled standards as a requirements checklist organized by principle."""
    data = load_dimension_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if data is None:
        return _NO_STANDARDS_FOR_DIM
    lines = []
    for principle, reqs in _principles_with_requirements(data):
        name = _require_field(principle, "name", "principle")
        lines.append(f"### {name}")
        if principle.get("description"):
            lines.append(principle["description"])
        for req, req_id, text in _resolved_requirements(reqs, overrides):
            req_line = f"- **{req_id}**: {text}"
            if req.get("description"):
                req_line += f" — {req['description']}"
            lines.append(req_line)
        lines.append("")
    return "\n".join(lines)


def render_compact_standards(
    compiled_dir: Path,
    dimension: str,
    evaluators_dir: Path | None = None,
    overrides: dict[str, dict] | None = None,
) -> str:
    """Render a compact standards checklist as JSON for the AI analyzer.

    Returns a compact JSON array grouped by principle with requirement IDs
    and rules. No pretty-printing — minimizes token usage.
    """
    data = load_dimension_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if data is None:
        return _NO_STANDARDS_FOR_DIM
    checklist = []
    for principle, reqs in _principles_with_requirements(data):
        requirements = [
            {"id": req_id, "rule": text}
            for _req, req_id, text in _resolved_requirements(reqs, overrides)
        ]
        checklist.append({
            "principle": principle.get("name", "Unknown"),
            "requirements": requirements,
        })
    return json.dumps(checklist, separators=(",", ":"))


def render_dimensions(dimensions_data: dict, dimension: str) -> str:
    """Format dimension info for prompt inclusion."""
    applies = dimensions_data.get("applies", [])
    dim_entry = None
    for d in applies:
        d_id = _require_field(d, _FIELD_ID, "dimension")
        if d_id == dimension:
            dim_entry = d
            break

    if not dim_entry:
        return f"_Dimension '{dimension}' not configured._"

    lines = [
        f"**Dimension:** {dimension}",
        f"**Weight:** {dim_entry.get('weight', 1.0)}",
    ]

    iso = dim_entry.get("iso_25010")
    if iso:
        lines.append(f"**ISO 25010:** {iso}")

    source = dim_entry.get("source")
    if source:
        lines.append(f"**Source:** {source}")

    return "\n".join(lines)
