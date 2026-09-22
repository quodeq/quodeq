"""Copy/replace mechanics behind the shared-repo publish staging.

Selection policy (what gets published) stays in services/shared_publish;
these helpers own only the shutil/os mechanics. Errors must propagate —
the publish flow converts them to PublishError at its own boundary.
"""
from __future__ import annotations

import json

import pytest

from quodeq.data.fs.run_artifacts import (
    copy_file_if_exists,
    copy_matching_files,
    ensure_dir,
    replace_json_file,
)


class TestEnsureDir:
    def test_creates_nested_and_is_idempotent(self, tmp_path):
        target = tmp_path / "a" / "b"
        ensure_dir(target)
        ensure_dir(target)
        assert target.is_dir()


class TestCopyFileIfExists:
    def test_copies_when_present(self, tmp_path):
        src = tmp_path / "status.json"
        src.write_text('{"state": "done"}')
        dest = tmp_path / "out.json"
        assert copy_file_if_exists(src, dest) is True
        assert dest.read_text() == '{"state": "done"}'

    def test_skips_when_absent(self, tmp_path):
        dest = tmp_path / "out.json"
        assert copy_file_if_exists(tmp_path / "missing", dest) is False
        assert not dest.exists()

    def test_missing_dest_parent_raises(self, tmp_path):
        src = tmp_path / "f"
        src.write_text("x")
        with pytest.raises(OSError):
            copy_file_if_exists(src, tmp_path / "no-dir" / "f")


class TestCopyMatchingFiles:
    def test_pattern_bounded_and_creates_dest(self, tmp_path):
        src_dir = tmp_path / "evidence"
        src_dir.mkdir()
        (src_dir / "a_evidence.jsonl").write_text("a")
        (src_dir / "b_evidence.jsonl").write_text("b")
        (src_dir / "stray.txt").write_text("no")
        dest_dir = tmp_path / "dest" / "evidence"

        copy_matching_files(src_dir, dest_dir, "*_evidence.jsonl")

        assert sorted(p.name for p in dest_dir.iterdir()) == [
            "a_evidence.jsonl", "b_evidence.jsonl",
        ]


class TestReplaceJsonFile:
    def test_writes_json_and_leaves_no_tmp(self, tmp_path):
        path = tmp_path / "published.json"
        replace_json_file(path, {"publishedBy": "me"})
        assert json.loads(path.read_text()) == {"publishedBy": "me"}
        assert list(tmp_path.iterdir()) == [path]

    def test_replaces_existing_content(self, tmp_path):
        path = tmp_path / "published.json"
        path.write_text('{"old": true}')
        replace_json_file(path, {"new": 1})
        assert json.loads(path.read_text()) == {"new": 1}

    def test_temp_file_is_not_the_predictable_name(self, tmp_path, monkeypatch):
        # The old implementation used path.with_suffix(path.suffix + ".tmp"),
        # a fixed, predictable name two concurrent writers could collide on.
        # mkstemp must be used instead, so capture the name it hands back.
        import quodeq.data.fs.run_artifacts as run_artifacts_mod

        seen_tmp_paths = []
        real_mkstemp = run_artifacts_mod.tempfile.mkstemp

        def spying_mkstemp(*args, **kwargs):
            fd, tmp_path_str = real_mkstemp(*args, **kwargs)
            seen_tmp_paths.append(tmp_path_str)
            return fd, tmp_path_str

        monkeypatch.setattr(run_artifacts_mod.tempfile, "mkstemp", spying_mkstemp)

        path = tmp_path / "published.json"
        predictable_name = str(path.with_suffix(path.suffix + ".tmp"))
        replace_json_file(path, {"a": 1})

        assert len(seen_tmp_paths) == 1
        assert seen_tmp_paths[0] != predictable_name
        # Atomically replaced: only the final file remains, no leftover temp.
        assert list(tmp_path.iterdir()) == [path]

    def test_temp_file_cleaned_up_on_write_failure(self, tmp_path, monkeypatch):
        import quodeq.data.fs.run_artifacts as run_artifacts_mod

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(run_artifacts_mod.os, "replace", boom)

        path = tmp_path / "published.json"
        with pytest.raises(OSError):
            replace_json_file(path, {"a": 1})

        # No leftover temp file, and the destination was never created.
        assert list(tmp_path.iterdir()) == []
