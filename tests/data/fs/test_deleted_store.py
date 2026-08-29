"""deleted.json format + lock mechanics live in the data layer;
services/deleted.py keeps only the business rules."""
from __future__ import annotations

import json

from quodeq.data.fs.deleted_store import (
    deleted_path,
    locked_deleted_store,
    read_deleted_entries,
    write_deleted_entries,
)


class TestReadDeletedEntries:
    def test_missing_returns_empty_list(self, tmp_path):
        assert read_deleted_entries(tmp_path) == []

    def test_corrupt_returns_empty_list(self, tmp_path):
        (tmp_path / "deleted.json").write_text("{nope")
        assert read_deleted_entries(tmp_path) == []

    def test_non_list_json_returns_empty_list(self, tmp_path):
        (tmp_path / "deleted.json").write_text('{"a": 1}')
        assert read_deleted_entries(tmp_path) == []

    def test_round_trip(self, tmp_path):
        entries = [{"dimension": "security", "principle": "P", "file": "f.py"}]
        write_deleted_entries(tmp_path, entries)
        assert read_deleted_entries(tmp_path) == entries


class TestWriteDeletedEntries:
    def test_empty_list_removes_the_file(self, tmp_path):
        write_deleted_entries(tmp_path, [{"file": "f.py"}])
        assert deleted_path(tmp_path).exists()
        write_deleted_entries(tmp_path, [])
        assert not deleted_path(tmp_path).exists()

    def test_empty_list_with_no_file_is_a_noop(self, tmp_path):
        write_deleted_entries(tmp_path, [])
        assert not deleted_path(tmp_path).exists()

    def test_writes_indented_json_list(self, tmp_path):
        write_deleted_entries(tmp_path, [{"file": "f.py"}])
        data = json.loads(deleted_path(tmp_path).read_text())
        assert isinstance(data, list)


class TestLockedDeletedStore:
    def test_creates_lock_file_and_releases(self, tmp_path):
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        with locked_deleted_store(project_dir):
            assert (project_dir / "deleted.json.lock").exists()
        # Re-acquiring after release must not block or raise.
        with locked_deleted_store(project_dir):
            pass

    def test_creates_missing_project_dir_for_the_lock(self, tmp_path):
        project_dir = tmp_path / "not-yet"
        with locked_deleted_store(project_dir):
            assert (project_dir / "deleted.json.lock").exists()
