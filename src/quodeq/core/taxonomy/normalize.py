"""Map a model-emitted violation-type tag onto a requirement's canonical code."""
from __future__ import annotations

from quodeq.core.taxonomy._fold import fold, fold_tokens
from quodeq.core.taxonomy.model import OTHER, RequirementTypes, Taxonomy


def _match(folded: str, types: RequirementTypes) -> str | None:
    if folded in types.codes:
        return folded
    return types.aliases.get(folded)


def _match_tokens(folded: str, types: RequirementTypes) -> str | None:
    key = fold_tokens(folded)
    for code in types.codes:
        if fold_tokens(code) == key:
            return code
    for alias, code in types.aliases.items():
        if fold_tokens(alias) == key:
            return code
    return None


def canonicalize(taxonomy: Taxonomy, req_id: str | None, raw_vt: object) -> str:
    """Return the canonical code for *raw_vt* under *req_id*.

    Order: fold; exact code; alias; token-folded code or alias; else OTHER.
    A requirement with no declared types (or an unknown requirement) returns
    the folded tag unchanged, or OTHER when empty: the transitional
    behaviour before a taxonomy exists. Idempotent: a code maps to itself.
    """
    folded = fold(raw_vt)
    if not folded:
        return OTHER
    types = taxonomy.for_requirement(req_id)
    if types is None or not types.codes:
        return folded
    return _match(folded, types) or _match_tokens(folded, types) or OTHER
