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

from quodeq.core.utils.io import read_json
from quodeq.core.standards.overrides import resolve_requirement_text

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


def extract_requirements(data: dict, overrides: dict[str, dict] | None = None) -> dict[str, dict]:
    """Extract {req_id: {principle, text}} from a compiled-standards dict.

    When *overrides* is supplied, requirement text placeholders are resolved
    using the per-requirement override values (see
    :func:`quodeq.core.standards.overrides.resolve_requirement_text`).

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
                "text": resolve_requirement_text(req, (overrides or {}).get(req_id)),
            }
    return lookup


def extract_requirement_checks(data: dict) -> dict[str, frozenset[str]]:
    """Extract ``{check_name: {req_id, ...}}`` from a compiled-standards dict.

    A requirement opts into a deterministic checker by naming it
    (``"check": "framework-imports"``). Grouping by checker name lets the
    caller run each one once no matter how many requirements it answers, then
    filter the judgments back to the requirements that actually asked.

    Requirements without a ``check`` are absent from the result, so a standard
    that declares none costs nothing.
    """
    grouped: dict[str, set[str]] = {}
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            name = req.get("check")
            req_id = req.get("id")
            if isinstance(name, str) and name and req_id:
                grouped.setdefault(name, set()).add(req_id)
    return {name: frozenset(ids) for name, ids in grouped.items()}


# ---------------------------------------------------------------------------
# The one I/O function core still owns.
#
# ``core/evidence/_refs.enrich_judgment`` resolves requirement refs while
# parsing judgments, and ``compiled_dir`` is threaded to it from 15 call
# sites. Until enrichment moves out of the parse path (its own workstream),
# core needs this read. Every OTHER standards loader lives in
# ``data/fs/standards_loader.py``.
# ---------------------------------------------------------------------------

def _load_compiled_data(
    compiled_dir: str | Path | None, dimension: str | None,
    evaluators_dir: Path | None = None,
) -> dict | None:
    """Load raw compiled standards JSON from *compiled_dir*. Returns None on error.

    Falls back to *evaluators_dir* for custom evaluators when provided.
    """
    if not dimension:
        return None
    if compiled_dir:
        path = Path(compiled_dir) / f"{dimension}.json"
        if path.is_file():
            try:
                return read_json(path)
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                _logger.warning("Failed to load compiled standards for %s: %s", dimension, exc)
                return None
    if evaluators_dir:
        evaluators_path = evaluators_dir / f"{dimension}.json"
        if evaluators_path.is_file():
            try:
                return read_json(evaluators_path)
            except (OSError, ValueError, UnicodeDecodeError):
                return None
    return None


def load_compiled_refs(
    compiled_dir: str | Path | None, dimension: str | None,
    evaluators_dir: Path | None = None,
) -> dict[str, list[dict]]:
    """Load ``{req_id: [{label, url, ...}, ...]}`` from compiled standards on disk."""
    data = _load_compiled_data(compiled_dir, dimension, evaluators_dir=evaluators_dir)
    if not data:
        return {}
    return extract_refs(data)
