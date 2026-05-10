"""Content hashing helpers — file, standards, prompts.

Post-V2 (B6.2c): the V1 fingerprint persistence machinery
(``build_fingerprint``, ``save_fingerprint``, ``load_fingerprint``,
``find_previous_fingerprint``, ``_queue_taken_files``) is gone. V2's
content-addressed cache replaces it: per-file entries keyed by a
SHA-256 of every input that affects analysis output.

What survives here are the hash primitives V2 uses to build cache
keys (and that priority scoring uses to detect file changes).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from quodeq.config.paths import default_paths

_HASH_CHUNK_SIZE = 1 << 16  # 64 KiB


def _hash_file(path: Path) -> str | None:
    """SHA-256 hash of a file's content, streamed in chunks to limit memory."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(_HASH_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _hash_standards(standards_dir: Path, dimension: str) -> str | None:
    """SHA-256 of the compiled standards JSON for a dimension.

    Uses the same chunked hashing approach as ``_hash_file`` to avoid
    reading the entire file into memory at once.
    """
    compiled = standards_dir / "compiled" / f"{dimension}.json"
    if not compiled.exists():
        return None
    return _hash_file(compiled)


# Prompts in this set carry the rules that classify a finding (what counts
# as a violation). A change here forces a full re-analysis. Other prompt
# files are framing/scaffolding; their changes flow into the next run's
# prompts naturally without invalidating cached results.
_RULES_BEARING_PROMPTS: frozenset[str] = frozenset({"evaluation_rules.md"})


def _hash_prompts_map(prompts_dir: Path | None = None) -> dict[str, str]:
    """Per-file SHA-256 of every *.md prompt under *prompts_dir*.

    V2's cache key folds these into one combined hash; storing per-file
    enables future selective invalidation if needed.
    """
    if prompts_dir is None:
        prompts_dir = default_paths().prompts_dir
    if prompts_dir is None or not prompts_dir.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(prompts_dir.glob("*.md")):
        h = _hash_file(path)
        if h:
            out[path.name] = h
    return out
