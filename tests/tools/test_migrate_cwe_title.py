"""#710 — migrate_cwe_title must not raise when json.loads returns a non-dict."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# tools/ is importable via conftest.py sys.path insert


class TestBuildCweNameLookupNonDict:
    def test_list_payload_is_skipped(self, tmp_path: Path) -> None:
        from migrate_cwe_title import _build_cwe_name_lookup
        f = tmp_path / "sec.json"
        f.write_text(json.dumps([{"principles": []}]), encoding="utf-8")
        # Must not raise AttributeError; bad file is skipped
        result = _build_cwe_name_lookup(tmp_path)
        assert result == {}

    def test_string_payload_is_skipped(self, tmp_path: Path) -> None:
        from migrate_cwe_title import _build_cwe_name_lookup
        f = tmp_path / "sec.json"
        f.write_text('"just a string"', encoding="utf-8")
        result = _build_cwe_name_lookup(tmp_path)
        assert result == {}

    def test_null_payload_is_skipped(self, tmp_path: Path) -> None:
        from migrate_cwe_title import _build_cwe_name_lookup
        f = tmp_path / "sec.json"
        f.write_text("null", encoding="utf-8")
        result = _build_cwe_name_lookup(tmp_path)
        assert result == {}

    def test_valid_dict_is_still_processed(self, tmp_path: Path) -> None:
        from migrate_cwe_title import _build_cwe_name_lookup
        data = {
            "principles": [
                {"cwes": [{"id": 306, "name": "Missing Authentication"}]}
            ]
        }
        f = tmp_path / "sec.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = _build_cwe_name_lookup(tmp_path)
        assert result == {306: "Missing Authentication"}


class TestMigrateFileNonDict:
    def test_list_payload_is_skipped_gracefully(self, tmp_path: Path) -> None:
        from migrate_cwe_title import migrate_file
        f = tmp_path / "eval.json"
        f.write_text(json.dumps([{"violations": []}]), encoding="utf-8")
        v, c = migrate_file(f, {}, apply=False)
        assert v == 0
        assert c == 0

    def test_null_payload_is_skipped_gracefully(self, tmp_path: Path) -> None:
        from migrate_cwe_title import migrate_file
        f = tmp_path / "eval.json"
        f.write_text("null", encoding="utf-8")
        v, c = migrate_file(f, {}, apply=False)
        assert v == 0
        assert c == 0
