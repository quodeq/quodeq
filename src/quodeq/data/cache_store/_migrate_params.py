"""Rebuilding a schema-3 entry's ``params_hash`` from what it stored.

Split out of ``migrate.py`` (which is at the file-length ratchet) as its own
responsibility: the migration walk re-keys and indexes entries, while this
module reconstructs the one key input schema-3 entries do not carry as a
hash. Moved verbatim, and re-exported from ``migrate`` for the callers and
tests that import it from there.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.standards.overrides import (
    hash_non_default_params,
    non_default_from_effective,
)


def derive_params_hash(
    dimension: str, effective_params: dict, standards_dir: Path | None,
    _cache: dict[tuple[str, str], dict] | None = None,
) -> str:
    """Rebuild a schema-3 entry's ``params_hash`` from its stored effective params.

    The writer hashed the non-default subset against the compiled defaults
    (``analysis.fingerprint._compute_dimension_params``). Diff the stored
    effective map against the current compiled defaults and hash the same way.
    "" when there is nothing to compare (no params, no standards dir, no or
    malformed compiled file), which is exactly what such entries were keyed
    under.
    """
    if not effective_params or standards_dir is None:
        return ""
    if _cache is None:
        _cache = {}
    k = (str(standards_dir), dimension)
    if k not in _cache:
        c = Path(standards_dir) / "compiled" / f"{dimension}.json"
        try:
            _cache[k] = json.loads(c.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - same rationale as the writer: never abort
            return ""
    try:
        return hash_non_default_params(non_default_from_effective(_cache[k], effective_params))
    except (AttributeError, TypeError):
        return ""
