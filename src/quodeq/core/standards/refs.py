"""Shared reference-label and compiled-refs utilities.

Used by both evidence_parser.py and mcp_findings.py to avoid duplicating
ref-label formatting and compiled-standards extraction logic.

Only pure logic (ref_label, extract_refs, extract_requirements,
extract_requirement_checks) lives here in the core layer.  The ``load_*``
helpers that perform file I/O live in ``data/fs/standards_loader.py``;
callers that already have loaded data should prefer the ``extract_*``
functions.
"""
from __future__ import annotations

from quodeq.core.standards.overrides import resolve_requirement_text

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
