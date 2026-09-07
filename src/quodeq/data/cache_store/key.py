"""Cache key: content-addressed identity for a (file, dimension) work unit.

The key is the SHA-256 of a canonical JSON serialization of the inputs that
define "this exact code, evaluated for this dimension". Two runs with
identical inputs compute the same key and share the cached result.

The key is permissive (cost-first): it invalidates ONLY on a real per-unit
change. Evaluations are expensive and the user owns the explicit refresh
path (``--clean-scan``), so cached findings stay resilient to everything
except an actual file change.

Intentionally NOT in the key (recorded in ``CacheEntry.provenance`` instead,
so reuse across these boundaries is surfaced rather than silently
re-evaluated): ``model_id``, ``prompts_hash``, ``standards_hash``,
``evaluator_hash``, sampling params, timestamps, run/machine/user/git
metadata, and, since schema 4, the project ``language``. Language reached
the prompt only as a heading word and never filtered files, yet a
``detect_language()`` flip (e.g. ``build.gradle`` -> ``build.gradle.kts``)
re-keyed 100% of a repo.

``file_path`` stays: clean-architecture reads layer directories from the
prompt and ``path_role`` infers test vs production from it. A moved file with
unchanged content is recovered by adoption (``analysis.cache._adoption``),
not by loosening the key.

``params_hash`` stays: a threshold override rewrites the rule text the model
enforces. It is "" (and absent from the canonical form) when every param
equals its default.

This module lives in the data layer so the schema migration can compute
keys without importing ``analysis``. ``quodeq.analysis.cache.key`` re-exports
it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

# Bumped on any breaking change to key composition or entry format.
# v1 -> v2: file_done marker contract.
# v2 -> v3: permissive key; model/prompts/standards/sampling moved to
#           provenance. Entries became self-describing (content hash stored).
# v3 -> v4: ``language`` left the key. Migrated losslessly by
#           ``data.cache_store.migrate`` from the stored fields.
SCHEMA_VERSION = 4


@dataclass(frozen=True)
class CacheKey:
    """The real per-unit inputs that determine the analysis output.

    Adding a field here is a cache-wide re-key, so do it only for a genuine
    per-unit input, and add the matching migration step.
    """

    schema_version: int
    file_content_hash: str
    file_path: str
    dimension: str
    # Per-dimension hash of non-default threshold params ("" when all
    # defaults). Empty is omitted from the canonical form so default-config
    # keys stay byte-identical to pre-params keys.
    params_hash: str = ""


def compute_key(key: CacheKey) -> str:
    """Return the hex SHA-256 of the canonical serialization of ``key``."""
    data = asdict(key)
    if not data["params_hash"]:
        del data["params_hash"]
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
