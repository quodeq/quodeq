"""Use case: per-project standards threshold override analysis.

Extracted from api/standards_overrides_routes.py so the count/diff logic is
testable without an HTTP request; the route keeps only request parsing and
response shaping.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.standards.overrides import dimension_params
from quodeq.services.standards_prefs import iter_compiled_standards


def override_counts_by_dimension(overrides: dict, compiled_dir: Path) -> dict[str, int]:
    """Per-dimension count of overridden requirements, keyed by compiled id."""
    dim_by_req: dict[str, str] = {}
    for stem, data in iter_compiled_standards(compiled_dir):
        for principle in data.get("principles", []):
            for req in principle.get("requirements", []):
                if req.get("id"):
                    dim_by_req[req["id"]] = data.get("id", stem)
    counts: dict[str, int] = {}
    for req_id in overrides:
        dim = dim_by_req.get(req_id)
        if dim:
            counts[dim] = counts.get(dim, 0) + 1
    return counts


def changed_dimensions(compiled_dir: Path, current: dict, proposed: dict) -> list[str]:
    """Dimensions whose non-default effective params differ between the
    current overrides file and the proposed mapping. A changed dimension is
    exactly one whose cache keys will shift, so this is the invalidation
    impact surfaced to the user before saving.

    Scans only the compiled dir, mirroring dimension_params_state (which reads
    only compiled/<dimension>.json), so custom evaluator-dir standards—whose
    cache keys never shift on override change—are symmetrically never reported."""
    changed: list[str] = []
    for stem, data in iter_compiled_standards(compiled_dir):
        try:
            _, before = dimension_params(data, current)
            _, after = dimension_params(data, proposed)
        except (AttributeError, TypeError):
            # A shape-invalid params block (spec not a dict, "params" not a
            # mapping, etc.) raises AttributeError/TypeError out of
            # dimension_params -- same degrade-and-skip as an unreadable or
            # unparseable compiled file, so a bad file never 500s the PUT.
            continue
        if before != after:
            changed.append(data.get("id", stem))
    return changed
