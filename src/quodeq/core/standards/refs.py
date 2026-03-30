"""Shared reference-label and compiled-refs utilities.

Used by both evidence_parser.py and mcp_findings.py to avoid duplicating
ref-label formatting and compiled-standards loading logic.

Pure logic (ref_label, extract_refs, extract_requirements) lives here in the
core layer.  The ``load_*`` convenience helpers that perform file I/O are thin
wrappers kept for backward compatibility; callers that already have loaded data
should prefer the ``extract_*`` functions.
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


# ---------------------------------------------------------------------------
# Pure extraction helpers — no file I/O, operate on pre-loaded data
# ---------------------------------------------------------------------------

def extract_refs(data: dict) -> dict[str, list[dict]]:
    """Extract {req_id: [{label, url, ...}, ...]} from a compiled-standards dict.

    This is the pure-logic counterpart of ``load_compiled_refs``.
    """
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


def extract_requirements(data: dict) -> dict[str, dict]:
    """Extract {req_id: {principle, text}} from a compiled-standards dict.

    This is the pure-logic counterpart of ``load_compiled_requirements``.
    """
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


# ---------------------------------------------------------------------------
# I/O convenience wrappers (kept for backward-compatible call-sites)
# ---------------------------------------------------------------------------

def _load_compiled_data(compiled_dir: str | Path | None, dimension: str | None) -> dict | None:
    """Load raw compiled standards JSON from *compiled_dir*. Returns None on error.

    This is an I/O adapter — callers that already have the data should use
    :func:`extract_refs` or :func:`extract_requirements` directly.
    """
    if not compiled_dir or not dimension:
        return None
    try:
        return read_json(Path(compiled_dir) / f"{dimension}.json")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to load compiled standards for %s: %s", dimension, exc)
        return None


def load_compiled_refs(compiled_dir: str | Path | None, dimension: str | None) -> dict[str, list[dict]]:
    """Load {req_id: [{label, url, ...}, ...]} from compiled standards on disk.

    Returns an empty dict on any I/O or parse error (logged as a warning).
    Prefer :func:`extract_refs` when data is already loaded.
    """
    data = _load_compiled_data(compiled_dir, dimension)
    if not data:
        return {}
    return extract_refs(data)


def load_compiled_refs_multi(
    compiled_dir: str | Path | None, dimensions: list[str],
) -> dict[str, list[dict]]:
    """Load refs for multiple dimensions, merging into a single lookup."""
    merged: dict[str, list[dict]] = {}
    for dim in dimensions:
        merged.update(load_compiled_refs(compiled_dir, dim))
    return merged


def load_compiled_requirements_multi(
    compiled_dir: str | Path | None, dimensions: list[str],
) -> dict[str, dict]:
    """Load requirements for multiple dimensions, merging into a single lookup."""
    merged: dict[str, dict] = {}
    for dim in dimensions:
        merged.update(load_compiled_requirements(compiled_dir, dim))
    return merged


def load_compiled_requirements(compiled_dir: str | Path | None, dimension: str | None) -> dict[str, dict]:
    """Load {req_id: {principle, text}} from compiled standards on disk.

    Used by the MCP server to auto-fill principle name and requirement text
    from the requirement ID, so the AI doesn't need to send them.
    Prefer :func:`extract_requirements` when data is already loaded.
    """
    data = _load_compiled_data(compiled_dir, dimension)
    if not data:
        return {}
    return extract_requirements(data)
