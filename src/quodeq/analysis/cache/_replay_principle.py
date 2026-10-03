"""Replayed cache findings go through admission, like fresh ones.

A cache entry keeps the finding as it was first written, and the cache key
ignores the standard on purpose, so an entry can predate the standard it is
replayed under (or have been written while that standard was not loaded).
Replay re-admits every finding with the run's standards: the evidence row
and the event get the same requirement, principle, dimension and refs, and
a finding the standard cannot place is kept as unmapped instead of being
graded under a blank principle. The cache entry itself stays as it was.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.mcp.finding_admission import admission_of, apply_admission, is_unplaceable
from quodeq.analysis.run_types import RunConfig
from quodeq.context.trust_model import TrustModel
from quodeq.core.admission import StandardCatalog
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.fs.standard_index_loader import load_standard_catalog
from quodeq.data.projection.standards_defaults import default_standards_dirs

CatalogLoader = Callable[[Iterable[str]], StandardCatalog]


@dataclass(frozen=True)
class ReplayPolicy:
    """What a replay applies to cached findings: the trust model the severity
    gates read, and the loader of the standards findings are re-admitted with."""

    trust_model: TrustModel | None = None
    catalog_loader: CatalogLoader | None = None


def replay_catalog_loader(config: RunConfig) -> CatalogLoader:
    """Loads this run's standards (custom evaluators first, then the built-in
    ones), or the install's when the run configures neither."""
    compiled = config.standards_dir / "compiled" if config.standards_dir else None
    evaluators = config.evaluators_dir
    if compiled is None and evaluators is None:
        compiled, evaluators = default_standards_dirs()

    def load(dimensions: Iterable[str]) -> StandardCatalog:
        return load_standard_catalog(
            sorted({d for d in dimensions if d}), evaluators_dir=evaluators,
            compiled_dir=Path(compiled) if compiled else None,
        )
    return load


def readmit(findings: list[dict], catalog: StandardCatalog | None, *, log: LogSink = NULL_LOG) -> list[dict]:
    """Copies of *findings* with their standard-derived fields re-derived.

    Copy, do not mutate: the dicts belong to the cache entries. A finding whose
    dimension has no loaded standard is copied unchanged.
    """
    out: list[dict] = []
    for finding in findings:
        copy = dict(finding)
        if catalog is not None:
            # Within the finding's own dimension, as projection does: the
            # live path already routed it when the scan covered several.
            own = catalog.only([finding.get("d") or ""])
            placed = admission_of(finding, own, finding.get("d"))
            if not is_unplaceable(placed):
                apply_admission(copy, finding, placed, finding.get("d"), log)
        out.append(copy)
    return out
