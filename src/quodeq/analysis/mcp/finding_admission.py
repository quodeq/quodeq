"""The enricher's standards stage, through ``core.admission``.

Every writer that builds a finding from model or checker output places it
with ``admit``: the canonical requirement, principle, dimension and refs come
from the standard, never from what the model declared. A dimension with no
loaded standard passes through unchanged (nothing to derive from); a code the
loaded standard does not define is returned as ``Unmapped`` for the caller to
refuse or record.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from quodeq.analysis.mcp.ref_scoring import select_best_refs
from quodeq.core.standards.refs import ref_label
from quodeq.config.paths import default_paths
from quodeq.data.fs.standard_index_loader import load_standard_catalog
from quodeq.core.admission import (
    Admitted, FindingFacts, StandardCatalog, StandardIndex, Unmapped, UnmappedReason, admit,
)
from quodeq.core.observability import LogSink

ADMISSION_KEY = "admission"
ADMISSION_UNMAPPED = "unmapped"
UNMAPPED_REASON_KEY = "unmapped_reason"
REPORTED_REQ_KEY = "req_reported"
UNKNOWN_REQ_KEY = "req_unknown"


def run_catalog(compiled_dir: str | Path | None, dimensions: Iterable[str]) -> StandardCatalog:
    """The standards of a scan: custom evaluators first, then the compiled built-ins.

    The evaluators dir is the install's, the same fallback the run context
    uses; before admission the live path never read custom evaluators, so a
    custom standard's findings were written without a principle.
    """
    evaluators = default_paths().evaluators_dir
    return load_standard_catalog(
        [d for d in dimensions if d],
        evaluators_dir=evaluators if evaluators and evaluators.is_dir() else None,
        compiled_dir=Path(compiled_dir) if compiled_dir else None,
    )


def catalog_from_reqs(
    dimension: str | None, compiled_reqs: dict[str, dict], compiled_refs: dict[str, list[dict]],
) -> StandardCatalog:
    """A one-dimension catalog from the enricher's legacy requirement tables."""
    if not dimension or not compiled_reqs:
        return StandardCatalog.of([])
    mapping = {rid: r["principle"] for rid, r in compiled_reqs.items() if r.get("principle")}
    refs = {rid: tuple(v) for rid, v in compiled_refs.items()}
    return StandardCatalog.of([StandardIndex(dimension, mapping, refs)])


def admission_of(args: dict, catalog: StandardCatalog, scanned: str | None) -> Admitted | Unmapped:
    """*args* placed in the declared dimension's standard, else the scanned one's."""
    facts = FindingFacts.from_wire(args)
    declared = facts.dimension if catalog.get(facts.dimension) is not None else scanned
    return admit(facts, catalog, declared)


def is_unplaceable(placed: Admitted | Unmapped) -> bool:
    """True when there is no loaded standard to place the finding in."""
    return isinstance(placed, Unmapped) and placed.reason is UnmappedReason.NO_STANDARD


def dedup_identity(args: dict, placed: Admitted | Unmapped) -> object:
    """What the dedup key identifies a finding by: its requirement.

    The canonical id when placed, the reported code otherwise, and the
    principle only for a row with no code at all. The JSONL dedup and the SQL
    ``dedup_key`` use the same rule, so all three agree on what a duplicate is.
    """
    if isinstance(placed, Admitted):
        return placed.req or placed.facts.req or placed.principle
    return args.get("req") or args.get("p")


def apply_admission(
    finding: dict, args: dict, placed: Admitted | Unmapped, scanned: str | None, log: LogSink,
) -> Unmapped | None:
    """Write *placed*'s derived fields onto *finding*; return the Unmapped, if any.

    Callers handle ``no_standard`` themselves (see ``is_unplaceable``).
    """
    if isinstance(placed, Unmapped):
        finding.pop("p", None)
        finding.pop("req_refs", None)
        finding["d"] = placed.dimension or scanned
        finding[ADMISSION_KEY] = ADMISSION_UNMAPPED
        finding[UNMAPPED_REASON_KEY] = placed.reason.value
        return placed
    declared = args.get("d")
    if placed.routed and declared and declared != placed.dimension:
        log.warning(
            f"Rerouting finding from declared dimension {declared!r} to "
            f"{placed.dimension!r} per requirement {placed.req!r} "
            f"(severity={args.get('severity')}, file={args.get('file')})"
        )
    if placed.folded and args.get("req"):
        finding[REPORTED_REQ_KEY] = args["req"]
    if placed.unknown_req:
        finding[UNKNOWN_REQ_KEY] = True
    if placed.req:
        finding["req"] = placed.req
    finding["p"] = placed.principle
    finding["d"] = placed.dimension
    if placed.refs:
        best = select_best_refs(list(placed.refs), args.get("w", ""), args.get("reason", ""))
        # The standard's refs carry source/id but no label; the card names its links by label.
        finding["req_refs"] = [{**r, "label": r.get("label") or ref_label(r)} for r in best]
    else:
        finding.pop("req_refs", None)
    return None


def refusal_of(placed: Admitted | Unmapped, catalog: StandardCatalog) -> Unmapped | None:
    """The Unmapped to refuse the model with, or None when the code was valid.

    A finding placed only by the principle it named still carries a code the
    standard lacks, so the live path asks for a valid one first.
    """
    if isinstance(placed, Unmapped):
        return None if placed.reason is UnmappedReason.NO_STANDARD else placed
    if not placed.unknown_req:
        return None
    index = catalog.get(placed.dimension)
    nearest = index.nearest(placed.facts.req) if index is not None else ()
    return Unmapped(placed.facts, placed.dimension, UnmappedReason.UNKNOWN_REQUIREMENT, nearest)


def unmapped_feedback(placed: Unmapped, reported: str | None) -> str:
    """What the model is told when its requirement code does not exist."""
    code = reported or "(none)"
    hint = ", ".join(placed.nearest) if placed.nearest else "none"
    return (
        f"Requirement {code!r} is not in the {placed.dimension} standard, so the finding was not "
        f"recorded. Report it again with one of the standard's ids. Closest: {hint}."
    )
