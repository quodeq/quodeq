"""Cache entry — the persisted record for one cache key.

Stored as a single JSON file written atomically by the backend.
``findings`` mirrors the existing JSONL line schema, so a JSONL file is
just a stream of finding dicts and migration is mechanical.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# Bumped whenever the entry format itself changes shape. Independent of
# CacheKey.schema_version, which gates input-side invalidation.
ENTRY_FORMAT_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    created_at: str = field(default_factory=_utc_now)
    cache_format_version: int = ENTRY_FORMAT_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> CacheEntry:
        data = json.loads(text)
        return cls(**data)
