"""Tests for quodeq.services._standards_io — I/O helpers and data conversion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services._standards_io import (
    build_builtin_detail,
    build_builtin_meta,
    build_custom_meta,
    build_detail,
    count_principles_and_requirements,
    default_read_json,
    default_write_json,
    get_builtin_weight,
    is_builtin_id,
    load_cwe_entries,
)


class TestDefaultReadWriteJson:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "test.json"
        data = {"key": "value", "num": 42}
        default_write_json(path, data)
        result = default_read_json(path)
        assert result == data

    def test_read_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            default_read_json(tmp_path / "missing.json")

    def test_write_creates_file(self, tmp_path):
        path = tmp_path / "new.json"
        assert not path.exists()
        default_write_json(path, {"a": 1})
        assert path.exists()

    def test_write_overwrites(self, tmp_path):
        path = tmp_path / "test.json"
        default_write_json(path, {"old": True})
        default_write_json(path, {"new": True})
        assert default_read_json(path) == {"new": True}


class TestCountPrinciplesAndRequirements:
    def test_empty(self):
        assert count_principles_and_requirements({}) == (0, 0)

    def test_no_requirements(self):
        data = {"principles": [{"name": "P1"}, {"name": "P2"}]}
        assert count_principles_and_requirements(data) == (2, 0)

    def test_with_requirements(self):
        data = {
            "principles": [
                {"name": "P1", "requirements": [{"id": "R1"}, {"id": "R2"}]},
                {"name": "P2", "requirements": [{"id": "R3"}]},
            ]
        }
        assert count_principles_and_requirements(data) == (2, 3)

    def test_empty_requirements(self):
        data = {"principles": [{"name": "P1", "requirements": []}]}
        assert count_principles_and_requirements(data) == (1, 0)

    # --- #293: malformed persisted data must not crash ---

    def test_principles_not_a_list_returns_zero_counts(self):
        """principles as a dict (not a list) must not raise."""
        data = {"principles": {"P1": {"requirements": []}}}
        assert count_principles_and_requirements(data) == (0, 0)

    def test_principles_string_returns_zero_counts(self):
        data = {"principles": "bad value"}
        assert count_principles_and_requirements(data) == (0, 0)

    def test_non_dict_items_in_principles_are_skipped(self):
        """Non-dict items in the principles list are silently skipped."""
        data = {
            "principles": [
                "not a dict",
                42,
                {"name": "P1", "requirements": [{"id": "R1"}]},
                None,
            ]
        }
        # Only the one valid dict counts
        assert count_principles_and_requirements(data) == (1, 1)

    def test_mix_of_valid_and_invalid_principles(self):
        data = {
            "principles": [
                {"name": "P1", "requirements": [{"id": "R1"}, {"id": "R2"}]},
                "garbage",
                {"name": "P2", "requirements": []},
            ]
        }
        assert count_principles_and_requirements(data) == (2, 2)


class TestBuildDetail:
    def test_minimal(self):
        data = {"id": "sec-001"}
        detail = build_detail(data)
        assert detail.id == "sec-001"
        assert detail.name == "sec-001"
        assert detail.type == "custom"
        assert detail.managed is False

    def test_full(self):
        data = {
            "id": "sec-001",
            "name": "Security",
            "description": "Security standard",
            "weight": 2.0,
            "source": "ISO 25010",
            "type": "custom",
            "managed": True,
            "origin": "https://example.com",
            "origin_hash": "abc123",
            "principles": [{"name": "P1"}],
        }
        detail = build_detail(data)
        assert detail.name == "Security"
        assert detail.weight == 2.0
        assert detail.managed is True
        assert detail.origin == "https://example.com"
        assert len(detail.principles) == 1

    def test_type_default_override(self):
        data = {"id": "x"}
        detail = build_detail(data, type_default="builtin")
        assert detail.type == "builtin"


class TestBuildBuiltinDetail:
    def test_basic(self):
        data = {"name": "Security", "source": "ISO", "principles": []}
        detail = build_builtin_detail(data, "security", 1.5)
        assert detail.id == "security"
        assert detail.weight == 1.5
        assert detail.managed is True
        assert detail.source == "ISO"
        assert detail.type == "builtin"

    def test_sources_list(self):
        data = {"name": "Reliability", "sources": ["CWE", "OWASP"], "principles": []}
        detail = build_builtin_detail(data, "reliability", 1.0)
        assert detail.source == "CWE, OWASP"

    def test_no_source(self):
        data = {"name": "Test", "principles": []}
        detail = build_builtin_detail(data, "test", 1.0)
        assert detail.source == ""


class TestBuildCustomMeta:
    def test_minimal(self):
        data = {"id": "custom-1"}
        meta = build_custom_meta(data, 3, 10)
        assert meta.id == "custom-1"
        assert meta.principle_count == 3
        assert meta.requirement_count == 10
        assert meta.type == "custom"

    def test_full(self):
        data = {
            "id": "custom-1",
            "name": "My Standard",
            "description": "desc",
            "weight": 0.5,
            "source": "internal",
            "type": "custom",
            "managed": False,
            "origin": "http://origin",
            "origin_hash": "hash",
        }
        meta = build_custom_meta(data, 2, 5)
        assert meta.name == "My Standard"
        assert meta.weight == 0.5


class TestBuildBuiltinMeta:
    def test_basic(self):
        dim = {"id": "security", "iso_25010": "Security", "source": "ISO 25010"}
        meta = build_builtin_meta(dim, 5, 20)
        assert meta.id == "security"
        assert meta.name == "Security"
        assert meta.principle_count == 5
        assert meta.requirement_count == 20
        assert meta.managed is True

    def test_fallback_name(self):
        dim = {"id": "test", "name": "Test Dim"}
        meta = build_builtin_meta(dim, 1, 1)
        assert meta.name == "Test Dim"

    def test_no_name_fallback_to_id(self):
        dim = {"id": "custom"}
        meta = build_builtin_meta(dim, 0, 0)
        assert meta.name == "custom"


class TestGetBuiltinWeight:
    def test_found(self):
        dims = {"applies": [{"id": "security", "weight": 2.0}, {"id": "reliability", "weight": 1.5}]}
        assert get_builtin_weight(dims, "security") == 2.0

    def test_not_found(self):
        dims = {"applies": [{"id": "security", "weight": 2.0}]}
        assert get_builtin_weight(dims, "nonexistent") == 1.0

    def test_no_weight_key(self):
        dims = {"applies": [{"id": "security"}]}
        assert get_builtin_weight(dims, "security") == 1.0

    def test_empty_applies(self):
        assert get_builtin_weight({}, "anything") == 1.0

    def test_no_applies_key(self):
        assert get_builtin_weight({"other": []}, "x") == 1.0


class TestIsBuiltinId:
    def test_true(self):
        dims = {"applies": [{"id": "security"}, {"id": "reliability"}]}
        assert is_builtin_id(dims, "security") is True

    def test_false(self):
        dims = {"applies": [{"id": "security"}]}
        assert is_builtin_id(dims, "custom-thing") is False

    def test_empty(self):
        assert is_builtin_id({}, "anything") is False


class TestLoadCweEntries:
    def test_basic(self):
        entries = [
            {"id": "CWE-79", "name": "XSS", "abstraction": "Base", "dimensions": ["security"]},
            {"id": "CWE-89", "name": "SQL Injection"},
        ]
        result = load_cwe_entries(entries)
        assert len(result) == 2
        assert result[0]["id"] == "CWE-79"
        assert result[0]["abstraction"] == "Base"
        assert result[1]["abstraction"] == ""
        assert result[1]["dimensions"] == []

    def test_empty(self):
        assert load_cwe_entries([]) == []
