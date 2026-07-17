"""Cache key — content-addressed identity for a (file, dimension) work unit.

The key is the SHA-256 of a canonical JSON serialization of the inputs that
define *"this exact code, evaluated for this dimension."* Two runs with
identical inputs compute the same key and share the cached result.

The key is **permissive** (cost-first): it invalidates ONLY on a real
per-unit change. Evaluations are expensive, the user already owns the
explicit refresh path (``--clean-scan``), so cached findings stay resilient
to everything except an actual file change.

What is intentionally NOT in the key (recorded in ``CacheEntry.provenance``
instead, so reuse across these boundaries is surfaced rather than silently
re-evaluated):
- ``model_id`` — switching models reuses prior work; the user refreshes if
  they want the new model to re-run.
- ``prompts_hash`` / ``standards_hash`` — a quodeq update or a standards edit
  reuses prior work; ``--clean-scan`` refreshes on demand.
- ``evaluator_hash`` and sampling params (``temperature``, ``max_tokens``).
- timestamps, run_id, machine, user, git_commit, branch — run metadata, never
  inputs to the analysis itself.

``language`` stays in the key: it is a stable project property (not a quodeq
update) and changing it genuinely changes which files exist and how they are
analyzed.

``params_hash`` joins the key for the same reason: a threshold override
rewrites the rule text the model enforces, so results computed under a
different threshold answer a different question. It is "" (and absent from
the canonical form) when every param equals its default.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CacheKey:
    """The real per-unit inputs that determine the analysis output.

    Only these fields. Volatile inputs (model, prompts, standards, sampling)
    are deliberately excluded — they live in ``CacheEntry.provenance``. Adding
    a field here is a cache-wide invalidation, so do it only for a genuine
    per-unit input.
    """

    schema_version: int
    file_content_hash: str
    file_path: str
    dimension: str
    language: str
    # Per-dimension hash of non-default threshold params ("" when all
    # defaults). Unlike model/prompts/standards this IS a per-unit input:
    # it rewrites the rule text the LLM enforces, so a change genuinely
    # changes the analysis. Empty is omitted from the canonical form so
    # default-config keys stay byte-identical to pre-params keys.
    params_hash: str = ""


def compute_key(key: CacheKey) -> str:
    """Return the hex SHA-256 of the canonical serialization of ``key``."""
    data = asdict(key)
    # Legacy identity: default params serialize exactly like pre-params
    # keys, so existing caches survive the upgrade and removing every
    # override restores the original cached results.
    if not data["params_hash"]:
        del data["params_hash"]
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
