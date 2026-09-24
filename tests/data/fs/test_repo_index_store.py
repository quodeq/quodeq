"""Raw JSON read/write mechanics for the repo-identity index.

services/_repo_index.py decides what the index means (self-heal, key
matching) and owns the outer best-effort save semantics (log a warning and
swallow a write failure); this module owns the JSON file mechanics: the
same-dir temp file, the atomic replace, and a best-effort cleanup of that
temp file on failure.
"""
from __future__ import annotations

import json

import pytest

from quodeq.data.fs.repo_index_store import read_repo_index, write_repo_index


class TestReadRepoIndex:
    def test_empty_when_missing(self, tmp_path):
        assert read_repo_index(tmp_path / "missing.json") == {}

    def test_empty_when_corrupt(self, tmp_path):
        path = tmp_path / ".repo_index.json"
        path.write_text("{not valid json")
        assert read_repo_index(path) == {}

    def test_empty_when_not_an_object(self, tmp_path):
        path = tmp_path / ".repo_index.json"
        path.write_text("[1, 2]")
        assert read_repo_index(path) == {}

    def test_returns_parsed_index(self, tmp_path):
        path = tmp_path / ".repo_index.json"
        path.write_text(json.dumps({"key\x00path\x00": "uuid-1"}))
        assert read_repo_index(path) == {"key\x00path\x00": "uuid-1"}


class TestWriteRepoIndex:
    def test_writes_json_and_leaves_no_tmp(self, tmp_path):
        path = tmp_path / ".repo_index.json"
        write_repo_index(path, {"k": "v"})
        assert json.loads(path.read_text()) == {"k": "v"}
        assert list(tmp_path.iterdir()) == [path]

    def test_replaces_existing_content(self, tmp_path):
        path = tmp_path / ".repo_index.json"
        path.write_text('{"old": "1"}')
        write_repo_index(path, {"new": "2"})
        assert json.loads(path.read_text()) == {"new": "2"}

    def test_raises_on_write_failure(self, tmp_path, monkeypatch):
        import quodeq.data.fs.repo_index_store as repo_index_store_mod

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(repo_index_store_mod.os, "replace", boom)
        path = tmp_path / ".repo_index.json"
        with pytest.raises(OSError, match="disk full"):
            write_repo_index(path, {"a": "b"})

    def test_logs_debug_via_sink_when_cleanup_also_fails(self, tmp_path, recording_log, monkeypatch):
        import quodeq.data.fs.repo_index_store as repo_index_store_mod

        def raise_replace(*_a, **_k):
            raise OSError("target locked")

        def raise_unlink(*_a, **_k):
            raise OSError("cannot remove tmp")

        monkeypatch.setattr(repo_index_store_mod.os, "replace", raise_replace)
        monkeypatch.setattr(repo_index_store_mod.os, "unlink", raise_unlink)

        path = tmp_path / ".repo_index.json"
        with pytest.raises(OSError, match="target locked"):
            write_repo_index(path, {"a": "b"}, log=recording_log)

        assert recording_log.debug_messages
        assert "temp repo index file not removed after a failed save" in recording_log.debug_messages[0]
        # No warning here -- that is the caller's (save_repo_index's) job.
        assert recording_log.warning_messages == []
