"""Cache entry — JSON round-trip and shape."""
from __future__ import annotations

import json

from quodeq.analysis.cache.entry import CacheEntry, ENTRY_FORMAT_VERSION, build_provenance


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


def test_format_version_bumped_to_2():
    # The new self-describing entry (file_content_hash + provenance) is
    # format 2; the bump marks the shape change for any future migration.
    assert ENTRY_FORMAT_VERSION == 2


def test_file_content_hash_defaults_empty():
    # Self-describing: an entry records the content hash it was keyed under,
    # but the field is defaulted so legacy/partial construction still works.
    assert _make().file_content_hash == ""


def test_provenance_defaults_empty():
    assert _make().provenance == {}


def test_file_content_hash_round_trips():
    entry = _make(file_content_hash="deadbeef")
    assert CacheEntry.from_json(entry.to_json()).file_content_hash == "deadbeef"


def test_provenance_round_trips():
    prov = {
        "model_id": "claude-opus-4-7",
        "prompts_hash": "p123",
        "standards_hash": "s456",
        "quodeq_version": "1.1.2",
    }
    entry = _make(provenance=prov)
    assert CacheEntry.from_json(entry.to_json()).provenance == prov


def test_from_json_tolerates_legacy_format1_entry():
    # A format-1 entry on disk has no file_content_hash / provenance keys.
    # The read path must still load it, applying defaults, so an upgrade
    # never throws on an old entry.
    legacy = json.dumps({
        "key": "abc123",
        "schema_version": 2,
        "findings": [],
        "files_read": 1,
        "file_path": "a.py",
        "dimension": "security",
        "model_id": "claude-opus-4-7",
        "created_at": "2026-05-01T00:00:00+00:00",
        "cache_format_version": 1,
    })
    restored = CacheEntry.from_json(legacy)
    assert restored.file_content_hash == ""
    assert restored.language == ""
    assert restored.provenance == {}
    assert restored.cache_format_version == 1
    assert restored.model_id == "claude-opus-4-7"


def test_from_json_ignores_unknown_future_keys():
    # A newer quodeq may add entry fields. An older reader must IGNORE the
    # extra keys, not raise — a TypeError here makes LocalFileBackend.get
    # treat the entry as corrupt and DELETE it, destroying cached work that a
    # concurrent newer process may still be using (a destructive downgrade).
    future = json.dumps({
        "key": "abc123",
        "schema_version": 3,
        "findings": [],
        "files_read": 1,
        "file_path": "a.py",
        "dimension": "security",
        "model_id": "m",
        "a_field_a_future_quodeq_added": {"nested": 1},
    })
    restored = CacheEntry.from_json(future)
    assert restored.key == "abc123"
    assert restored.model_id == "m"


class TestProvenanceEffectiveParams:
    def test_build_provenance_records_effective_params(self):
        prov = build_provenance(
            model_id="m", prompts_hash="p", standards_hash="s", version="1.0",
            effective_params={"M-ANA-2": {"max_lines": 60}},
        )
        assert prov["effective_params"] == {"M-ANA-2": {"max_lines": 60}}

    def test_build_provenance_defaults_to_empty_params(self):
        prov = build_provenance(
            model_id="m", prompts_hash="p", standards_hash="s", version="1.0",
        )
        assert prov["effective_params"] == {}
