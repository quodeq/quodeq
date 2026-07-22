"""Cache entry — the persisted record for one cache key.

Stored as a single JSON file written atomically by the backend.
``findings`` mirrors the existing JSONL line schema, so a JSONL file is
just a stream of finding dicts and migration is mechanical.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone

# Bumped whenever the entry format itself changes shape. Independent of
# CacheKey.schema_version, which gates input-side invalidation.
# v1 -> v2: entry became self-describing — it now stores the
# ``file_content_hash`` it was keyed under plus a ``provenance`` block, so
# any future key change can be migrated losslessly by recomputing the key
# from stored fields instead of re-evaluating.
ENTRY_FORMAT_VERSION = 2


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def quodeq_version() -> str:
    """Best-effort current quodeq version string for provenance.

    Lazily imported so this module stays import-cheap and never raises if the
    package metadata is unavailable (e.g. running from an uninstalled tree)."""
    try:
        from quodeq import __version__  # noqa: PLC0415
        return __version__ or ""
    except Exception:  # noqa: BLE001 — provenance must never break a cache write
        return ""


def build_provenance(
    *, model_id: str | None, prompts_hash: str | None, standards_hash: str | None,
    version: str | None = None, effective_params: dict | None = None,
) -> dict:
    """Assemble the provenance block recorded on a cache entry.

    Single source of truth for the provenance shape, so the three cache-write
    sites (cache_writer, persist_dispatch_results, runner.analyze_unit) stay
    identical. ``version`` defaults to the current quodeq version.
    ``effective_params`` records the resolved threshold params the findings
    were judged under (``{req_id: {param: value}}``; ``{}`` when unknown)."""
    return {
        "model_id": model_id or "",
        "prompts_hash": prompts_hash or "",
        "standards_hash": standards_hash or "",
        "quodeq_version": version if version is not None else quodeq_version(),
        "effective_params": dict(effective_params) if effective_params else {},
    }


@dataclass
class CacheEntry:
    """One cached analysis result, keyed by ``key``."""

    key: str
    schema_version: int
    findings: list[dict]
    files_read: int
    file_path: str
    dimension: str
    model_id: str
    # Self-describing fields (format v2). ``file_content_hash`` and
    # ``language`` are the key fields not otherwise stored (``file_path`` and
    # ``dimension`` already are); together with them, an entry records EVERY
    # input its key was computed from, so any future cache-key change is
    # losslessly migratable (recompute from stored fields, no re-eval).
    # ``provenance`` records the volatile context the findings were produced
    # under (model, prompts, standards, quodeq version) so reuse across those
    # boundaries is never silent. All defaulted so format-1 entries still load.
    file_content_hash: str = ""
    language: str = ""
    provenance: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    cache_format_version: int = ENTRY_FORMAT_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> CacheEntry:
        data = json.loads(text)
        # Tolerate format drift in BOTH directions so a version mismatch never
        # throws (a throw would make LocalFileBackend treat the entry as
        # corrupt and DELETE it, destroying cached work):
        #  - older entry, missing new keys -> defaulted fields fill in;
        #  - newer entry, extra unknown keys -> ignore them.
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})
