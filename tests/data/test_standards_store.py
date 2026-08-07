"""Custom-standard file mechanics live in the data layer (T1 group C2).

services/_standards_crud composed paths, checked existence, mkdir'd and
unlinked inline (its JsonIO read/write was already injected); the library
importer wrote payloads with write_text. The path mechanics now live in
data/fs/standards_store.py; validation and permission decisions stay in
the services.
"""
from __future__ import annotations

import json

import pytest


class TestPathsAndExistence:
    def test_standard_path_composes(self, tmp_path):
        from quodeq.data.fs.standards_store import standard_path

        assert standard_path(tmp_path, "my-std") == tmp_path / "my-std.json"

    def test_exists_is_file_based(self, tmp_path):
        from quodeq.data.fs.standards_store import standard_exists

        assert standard_exists(tmp_path, "x") is False
        (tmp_path / "x.json").write_text("{}")
        assert standard_exists(tmp_path, "x") is True

    def test_ensure_evaluators_dir(self, tmp_path):
        from quodeq.data.fs.standards_store import ensure_evaluators_dir

        target = tmp_path / "nested" / "evaluators"
        ensure_evaluators_dir(target)
        assert target.is_dir()

    def test_remove_standard(self, tmp_path):
        from quodeq.data.fs.standards_store import remove_standard, standard_exists

        (tmp_path / "x.json").write_text("{}")
        remove_standard(tmp_path, "x")
        assert standard_exists(tmp_path, "x") is False


class TestJailedPayloadIo:
    def test_round_trip(self, tmp_path):
        from quodeq.data.fs.standards_store import (
            read_standard_payload, resolve_jailed_standard_path, write_standard_payload,
        )

        dest = resolve_jailed_standard_path(tmp_path, "lib-std")
        write_standard_payload(dest, {"id": "lib-std", "managed": True})
        assert json.loads(dest.read_text())["id"] == "lib-std"
        assert read_standard_payload(dest) == {"id": "lib-std", "managed": True}

    def test_read_missing_returns_none(self, tmp_path):
        from quodeq.data.fs.standards_store import read_standard_payload

        assert read_standard_payload(tmp_path / "nope.json") is None

    def test_jail_rejects_escape(self, tmp_path):
        from quodeq.data.fs.standards_store import resolve_jailed_standard_path

        with pytest.raises(ValueError):
            resolve_jailed_standard_path(tmp_path, "../escape")
