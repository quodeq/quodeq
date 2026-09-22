"""Unit tests for tools/enrich_standards.py.

``tools/`` is put on sys.path by tests/tools/conftest.py, so these imports
resolve at module level.
"""
from __future__ import annotations

import re

import pytest

import enrich_standards
from enrich_standards import _load_mapping, _load_prefix_map


def test_get_highest_id_skips_malformed_with_stderr_diagnostic(capsys):
    """Malformed requirement ids are skipped with a diagnostic to stderr."""
    reqs = [
        {"id": "ABC-001"},
        {"id": "ABC-002"},
        {"id": "ABC-malformed"},  # not a valid int
        {"id": "ABC-003"},
    ]

    result = enrich_standards._get_highest_id(reqs, "ABC")

    # Should skip the malformed one and return the highest valid number (3)
    assert result == 3

    # Should have logged the malformed id to stderr
    captured = capsys.readouterr()
    assert "Skipping malformed requirement id:" in captured.err
    assert "ABC-malformed" in captured.err


def test_get_highest_id_returns_zero_when_no_matching_prefix():
    """When no requirements match the prefix, returns 0."""
    reqs = [
        {"id": "XYZ-001"},
        {"id": "XYZ-002"},
    ]

    result = enrich_standards._get_highest_id(reqs, "ABC")

    assert result == 0


def test_get_highest_id_handles_only_valid_ids():
    """When all ids are valid, returns the highest number."""
    reqs = [
        {"id": "ABC-001"},
        {"id": "ABC-005"},
        {"id": "ABC-003"},
    ]

    result = enrich_standards._get_highest_id(reqs, "ABC")

    assert result == 5


class TestJsonLoaders:
    """_load_mapping / _load_prefix_map: parse, or exit naming the file."""

    def test_load_mapping_returns_parsed_json(self, tmp_path):
        f = tmp_path / "m.json"
        f.write_text('{"security": {"P1": [["text", [79]]]}}')
        assert _load_mapping(f) == {"security": {"P1": [["text", [79]]]}}

    def test_load_prefix_map_returns_parsed_json(self, tmp_path):
        f = tmp_path / "p.json"
        f.write_text('{"security": {"Confidentiality": "S-CON"}}')
        assert _load_prefix_map(f) == {"security": {"Confidentiality": "S-CON"}}

    def test_missing_mapping_exits_naming_the_file(self, tmp_path):
        missing = tmp_path / "absent.json"
        with pytest.raises(SystemExit, match=re.escape(f"Cannot load mapping file {missing}")):
            _load_mapping(missing)

    def test_malformed_prefix_map_exits_naming_the_file(self, tmp_path):
        f = tmp_path / "p.json"
        f.write_text("{not json")
        with pytest.raises(SystemExit, match=re.escape(f"Cannot load prefix map {f}")):
            _load_prefix_map(f)
