"""Cache entry — JSON round-trip and shape."""
from __future__ import annotations

from quodeq.analysis.cache.entry import CacheEntry, ENTRY_FORMAT_VERSION


def _make(**overrides) -> CacheEntry:
    defaults = dict(
        key="abc123",
        schema_version=1,
        findings=[{"file": "a.py", "line": 1, "t": "violation"}],
        files_read=1,
        file_path="a.py",
        dimension="security",
        model_id="claude-opus-4-7",
    )
    defaults.update(overrides)
    return CacheEntry(**defaults)


def test_round_trip_preserves_fields():
    original = _make()
    restored = CacheEntry.from_json(original.to_json())
    assert restored.key == original.key
    assert restored.findings == original.findings
    assert restored.files_read == original.files_read
    assert restored.dimension == original.dimension
    assert restored.model_id == original.model_id


def test_default_format_version_baked_in():
    entry = _make()
    assert entry.cache_format_version == ENTRY_FORMAT_VERSION


def test_created_at_is_iso_utc():
    entry = _make()
    assert "T" in entry.created_at
    assert entry.created_at.endswith("+00:00")


def test_empty_findings_round_trip():
    entry = _make(findings=[])
    assert CacheEntry.from_json(entry.to_json()).findings == []
