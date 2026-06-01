"""One-time garbage collection of cache entries from an older schema.

Changing the cache-key formula (the schema 2 -> 3 permissive-key change)
re-keys every entry: old entries land at paths current-schema lookups never
reach, so they can only waste disk. This module reclaims them once, lazily,
on the first cache open under a new schema.

Best-effort and idempotent: an entry that fails to read is skipped and
logged, never fatal; a second pass finds nothing left to remove. A per-root
marker file plus an in-process memo ensure the walk runs at most once per
schema per process.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

_logger = logging.getLogger(__name__)

# Mirrors local._ENTRY_FILENAME. Duplicated rather than imported so this
# module stays a leaf with no intra-package imports at load time (the GC is
# triggered from dimension_runner, not local).
_ENTRY_FILENAME = "entry.json"

# (root, schema) pairs already collected in this process.
_collected: set[tuple[str, int]] = set()


def _current_schema() -> int:
    # Lazy import: dimension_helpers is a heavier module (pulls RunConfig,
    # fingerprint, etc.) and imports this package's other cache modules.
    # Deferring keeps gc import-cheap and the dependency one-directional.
    from quodeq.analysis.cache.dimension_helpers import _SCHEMA_VERSION  # noqa: PLC0415
    return _SCHEMA_VERSION


def collect_legacy_entries(root: Path, *, min_schema: int) -> int:
    """Delete every cached entry whose ``schema_version`` is below *min_schema*.

    Returns the number of entries removed. Never raises: an entry that cannot
    be read is skipped and logged (we can't prove it's legacy, so we leave
    it). Safe to call repeatedly — a second pass removes nothing.
    """
    if not root.exists():
        return 0
    removed = 0
    for entry_path in root.rglob(_ENTRY_FILENAME):
        try:
            data = json.loads(entry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            _logger.debug("cache GC: skipping unreadable entry %s: %s", entry_path, exc)
            continue
        schema = data.get("schema_version")
        if isinstance(schema, int) and schema < min_schema:
            try:
                shutil.rmtree(entry_path.parent)
                removed += 1
            except OSError as exc:
                _logger.debug("cache GC: failed to remove %s: %s", entry_path.parent, exc)
    return removed


def maybe_collect_legacy_entries(root: Path) -> None:
    """Run the legacy-entry GC at most once per (root, schema) per process.

    Guarded by an in-process memo and an on-disk marker so the cache is
    walked at most once after an upgrade. A non-existent root is a cheap
    no-op — a brand-new cache has no legacy entries to reclaim.
    """
    schema = _current_schema()
    memo_key = (str(root), schema)
    if memo_key in _collected:
        return
    _collected.add(memo_key)
    if not root.exists():
        return
    marker = root / f".gc_schema_{schema}"
    try:
        if marker.exists():
            return
        removed = collect_legacy_entries(root, min_schema=schema)
        marker.write_text("", encoding="utf-8")
        if removed:
            _logger.info(
                "cache GC: reclaimed %d entr%s older than schema %d",
                removed, "y" if removed == 1 else "ies", schema,
            )
    except OSError as exc:  # marker write / unexpected IO — never fatal
        _logger.debug("cache GC: best-effort pass failed for %s: %s", root, exc)
