"""Shim: cache maintenance moved to ``data/cache_store/migrate``.

``ensure_cache_ready`` migrates schema-3 entries to schema 4, builds the
content index and reclaims legacy entries, once per cache root. This
analysis-side wrapper resolves the default standards directory (needed to
derive ``params_hash`` for entries written under threshold overrides) so
call sites in the pipeline stay a one-liner.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.data.cache_store.migrate import (  # noqa: F401 -- re-exports
    MigrationStats,
    collect_legacy_entries,
    migrate_entries,
)
from quodeq.data.cache_store.migrate import ensure_cache_ready as _ensure_cache_ready


def _default_standards_dir() -> Path | None:
    try:
        std = default_paths().standards_dir
    except Exception:  # noqa: BLE001 - maintenance must never break a scan
        return None
    return std if std is not None and std.exists() else None


def ensure_cache_ready(root: Path) -> None:
    """Migrate, index and GC *root* once per (root, schema). Never raises."""
    _ensure_cache_ready(root, standards_dir=_default_standards_dir())


# Back-compat name from the schema-3 GC era.
maybe_collect_legacy_entries = ensure_cache_ready
