"""Cache key — content-addressed identity for a (file, dimension) work unit.

The key is the SHA-256 of a canonical JSON serialization of every input
that affects the analysis output. Two runs with identical inputs compute
the same key and share the cached result; any diverging input produces
a different key and forces a fresh dispatch.

What is intentionally NOT in the key:
- timestamps, run_id, machine, user, git_commit, branch — those are
  metadata about the run, not inputs to the analysis itself.

What might be added later:
- evaluator code hash, when evaluators start shaping output deterministically.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CacheKey:
    """Inputs that uniquely determine the analysis output for one work unit."""

    schema_version: int
    file_content_hash: str
    file_path: str
    dimension: str
    standards_hash: str
    prompts_hash: str
    evaluator_hash: str
    model_id: str
    language: str
    # Sampling params: optional today, but baked into the key so any future
    # variation invalidates correctly without a schema bump.
    temperature: float | None = None
    max_tokens: int | None = None


def compute_key(key: CacheKey) -> str:
    """Return the hex SHA-256 of the canonical serialization of ``key``."""
    canonical = json.dumps(asdict(key), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
