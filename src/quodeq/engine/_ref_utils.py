"""Shared reference-label and compiled-refs utilities.

Used by both evidence_parser.py and mcp_findings.py to avoid duplicating
ref-label formatting and compiled-standards loading logic.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


def ref_label(ref: dict) -> str:
    """Build a display label for a ref (e.g. 'CWE-396', 'ERR08-J', 'WCAG 1.1.1').

    Recognises ``cwe``, ``wcag22``, and ``asvs`` source types; falls back to
    the raw ``id`` or uppercased ``source``.
    """
    source = ref.get("source", "")
    ref_id = ref.get("id")
    if source == "cwe" and ref_id:
        return f"CWE-{ref_id}"
    if source == "wcag22" and ref_id:
        return f"WCAG {ref_id}"
    if source == "asvs" and ref_id:
        return f"ASVS {ref_id}"
    if ref_id:
        return ref_id
    return source.upper() if source else "REF"


def load_compiled_refs(compiled_dir: str | Path | None, dimension: str | None) -> dict[str, list[dict]]:
    """Load {req_id: [{label, url, ...}, ...]} from compiled standards.

    Returns an empty dict on any I/O or parse error (logged as a warning).
    """
    if not compiled_dir or not dimension:
        return {}
    try:
        data = json.loads((Path(compiled_dir) / f"{dimension}.json").read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to load compiled standards for %s: %s", dimension, exc)
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
