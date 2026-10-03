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

    def test_read_non_object_raises(self, tmp_path):
        """A read failure must never look like "absent": that would let an
        import silently overwrite a user's corrupt standard file."""
        from quodeq.data.fs.standards_store import read_standard_payload

        path = tmp_path / "bad.json"
        path.write_text("[1, 2, 3]")
        with pytest.raises(ValueError, match="not a JSON object"):
            read_standard_payload(path)

    def test_read_corrupt_json_still_raises(self, tmp_path):
        from quodeq.data.fs.standards_store import read_standard_payload

        path = tmp_path / "bad.json"
        path.write_text("not json{{{")
        with pytest.raises(json.JSONDecodeError):
            read_standard_payload(path)

    def test_jail_rejects_escape(self, tmp_path):
        from quodeq.data.fs.standards_store import resolve_jailed_standard_path

        with pytest.raises(ValueError):
            resolve_jailed_standard_path(tmp_path, "../escape")


class TestAtomicWrite:
    def test_write_standard_payload_leaves_no_partial_file(self, tmp_path, monkeypatch):
        """A failed write keeps the previous standard intact and leaves no temp file."""
        import os

        from quodeq.data.fs.standards_store import write_standard_payload

        target = tmp_path / "s.json"
        target.write_text('{"old": true}')

        def _disk_full(fd, *_a, **_k):
            os.close(fd)
            raise OSError("disk full")

        monkeypatch.setattr("quodeq.data.fs.run_artifacts.dump_json_and_replace", _disk_full)
        with pytest.raises(OSError):
            write_standard_payload(target, {"new": True})
        assert json.loads(target.read_text()) == {"old": True}
        assert [p.name for p in tmp_path.iterdir()] == ["s.json"]

    def test_write_standard_payload_keeps_two_space_indent(self, tmp_path):
        from quodeq.data.fs.standards_store import write_standard_payload

        write_standard_payload(tmp_path / "s.json", {"a": 1})
        # Text-mode read: the writer uses the platform newline, as write_text did.
        assert (tmp_path / "s.json").read_text(encoding="utf-8") == '{\n  "a": 1\n}'
