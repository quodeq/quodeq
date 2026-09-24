"""Raw JSON read mechanics for the repo-identity index.

services/_repo_index.py decides what the index means (self-heal, key
matching, save-failure logging) and owns the write side; this module owns
only the read-side JSON parse.
"""
from __future__ import annotations

import json

from quodeq.data.fs.repo_index_store import read_repo_index


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
