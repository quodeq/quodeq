"""Template section renderers for analysis prompts."""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)

_NO_STANDARDS_FOR_DIM = "_No compiled standards for this dimension._"


def _load_dimension_data(
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
        _logger.warning("Failed to load dimension %s: %s", dimension, exc)
        return None


def render_compiled_standards(compiled_dir: Path, dimension: str, evaluators_dir: Path | None = None) -> str:
    """Render compiled standards as a requirements checklist organized by principle."""
    data = _load_dimension_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if data is None:
        return _NO_STANDARDS_FOR_DIM
    lines = []
    for principle in data.get("principles", []):
        reqs = principle.get("requirements", [])
        if not reqs:
            continue
        lines.append(f"### {principle['name']}")
        if principle.get("description"):
            lines.append(principle["description"])
        for req in reqs:
            req_line = f"- **{req['id']}**: {req['text']}"
            if req.get("description"):
                req_line += f" — {req['description']}"
            lines.append(req_line)
        lines.append("")
    return "\n".join(lines)


def render_compact_standards(compiled_dir: Path, dimension: str, evaluators_dir: Path | None = None) -> str:
    """Render a compact standards checklist for the AI analyzer.

    One line per requirement: ``REQ-ID: text``.
    No principle headings (server derives principle from req ID),
    no markdown formatting, no CWE refs (server enriches at report time).
    """
    data = _load_dimension_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if data is None:
        return _NO_STANDARDS_FOR_DIM
    lines = []
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            line = f"{req['id']}: {req['text']}"
            if req.get("description"):
                line += f" — {req['description']}"
            lines.append(line)
    return "\n".join(lines)


def render_dimensions(dimensions_data: dict, dimension: str) -> str:
    """Format dimension info for prompt inclusion."""
    applies = dimensions_data.get("applies", [])
    dim_entry = next((d for d in applies if d["id"] == dimension), None)

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
