"""Shared reference-label and compiled-refs utilities.

Used by both evidence_parser.py and mcp_findings.py to avoid duplicating
ref-label formatting and compiled-standards loading logic.
"""
from __future__ import annotations

import logging
from pathlib import Path

from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)

_SOURCE_CWE = "cwe"
_SOURCE_WCAG = "wcag22"
_SOURCE_ASVS = "asvs"


def ref_label(ref: dict) -> str:
    """Build a display label for a ref (e.g. 'CWE-396', 'ERR08-J', 'WCAG 1.1.1').

    Recognises ``cwe``, ``wcag22``, and ``asvs`` source types; falls back to
    the raw ``id`` or uppercased ``source``.
    """
    source = ref.get("source", "")
    ref_id = ref.get("id")
    if source == _SOURCE_CWE and ref_id:
        return f"CWE-{ref_id}"
    if source == _SOURCE_WCAG and ref_id:
        return f"WCAG {ref_id}"
    if source == _SOURCE_ASVS and ref_id:
        return f"ASVS {ref_id}"
    if ref_id:
        return ref_id
    return source.upper() if source else "REF"


def _load_compiled_data(compiled_dir: str | Path | None, dimension: str | None) -> dict | None:
    """Load raw compiled standards JSON. Returns None on error."""
    if not compiled_dir or not dimension:
        return None
    try:
        return read_json(Path(compiled_dir) / f"{dimension}.json")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to load compiled standards for %s: %s", dimension, exc)
        return None


def load_compiled_refs(compiled_dir: str | Path | None, dimension: str | None) -> dict[str, list[dict]]:
    """Load {req_id: [{label, url, ...}, ...]} from compiled standards.

    Returns an empty dict on any I/O or parse error (logged as a warning).
    """
    data = _load_compiled_data(compiled_dir, dimension)
    if not data:
        return {}
    lookup: dict[str, list[dict]] = {}
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            req_id = req.get("id")
            if not req_id:
                continue
            refs = [
                {"label": ref_label(r), "url": r["url"], "name": r.get("name", ""), "source": r.get("source", "")}
                for r in req.get("refs", []) if r.get("url")
            ]
            if refs:
                lookup[req_id] = refs
    return lookup


def load_compiled_requirements(compiled_dir: str | Path | None, dimension: str | None) -> dict[str, dict]:
    """Load {req_id: {principle, text}} from compiled standards.

    Used by the MCP server to auto-fill principle name and requirement text
    from the requirement ID, so the AI doesn't need to send them.
    """
    data = _load_compiled_data(compiled_dir, dimension)
    if not data:
        return {}
    lookup: dict[str, dict] = {}
    for principle in data.get("principles", []):
        principle_name = principle.get("name", "")
        for req in principle.get("requirements", []):
            req_id = req.get("id")
            if not req_id:
                continue
            lookup[req_id] = {
                "principle": principle_name,
                "text": req.get("text", ""),
            }
    return lookup
