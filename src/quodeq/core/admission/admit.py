"""Derive a finding's standard fields, or say why it cannot be placed."""
from __future__ import annotations

from quodeq.core.admission.facts import FindingFacts
from quodeq.core.admission.index import StandardCatalog, StandardIndex
from quodeq.core.admission.result import Admitted, Unmapped, UnmappedReason


def _admitted(facts: FindingFacts, index: StandardIndex, req: str, *, folded: bool,
              routed: bool = False) -> Admitted:
    return Admitted(
        facts=facts, dimension=index.dimension, req=req,
        principle=index.req_to_principle[req], refs=index.refs_for(req),
        folded=folded, routed=routed,
    )


def _by_requirement(facts: FindingFacts, index: StandardIndex, catalog: StandardCatalog,
                    raw: str) -> Admitted | None:
    if (hit := index.canonical(raw)) is not None:
        req, folded = hit
        return _admitted(facts, index, req, folded=folded)
    # Exact only when crossing dimensions: folding onto another standard's
    # id would guess between requirements the model never named.
    if (owner := catalog.owner_of(raw, besides=index.dimension)) is not None:
        return _admitted(facts, owner, raw, folded=False, routed=True)
    return None


def admit(facts: FindingFacts, catalog: StandardCatalog, dimension: str | None = None) -> Admitted | Unmapped:
    """Place *facts* in the standard of *dimension* (default: the facts' own).

    Order: the reported requirement code (exact, then folded, then another
    loaded dimension's exact id); then the principle hint read as a
    requirement id (deterministic checks write one there), then as a principle
    name (older rows, and findings whose code the standard lacks; flagged
    ``unknown_req``). Anything else is Unmapped, never a blank principle.
    """
    declared = dimension or facts.dimension
    index = catalog.get(declared)
    if index is None or not index.req_to_principle:
        return Unmapped(facts, declared, UnmappedReason.NO_STANDARD)
    if facts.req and (placed := _by_requirement(facts, index, catalog, facts.req)) is not None:
        return placed
    hint = facts.principle_hint
    if hint and not facts.req and (placed := _by_requirement(facts, index, catalog, hint)) is not None:
        return placed
    if hint and hint in index.principles:
        return Admitted(facts=facts, dimension=index.dimension, req=None, principle=hint,
                        unknown_req=bool(facts.req))
    if facts.req:
        return Unmapped(facts, index.dimension, UnmappedReason.UNKNOWN_REQUIREMENT,
                        index.nearest(facts.req))
    return Unmapped(facts, index.dimension, UnmappedReason.MISSING_REQUIREMENT,
                    index.nearest(hint))
