"""Tests for evaluation fingerprinting."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quodeq.analysis.fingerprint import build_fingerprint, load_fingerprint, save_fingerprint


class TestBuildFingerprint:
    def test_includes_file_hashes(self, tmp_path):
        (tmp_path / "a.py").write_text("content_a")
        (tmp_path / "b.py").write_text("content_b")
        fp = build_fingerprint(src=tmp_path, files=["a.py", "b.py"], dimension="security", standards_dir=None)
        assert "a.py" in fp["file_hashes"]
        assert "b.py" in fp["file_hashes"]
        assert fp["file_hashes"]["a.py"] == hashlib.sha256(b"content_a").hexdigest()

    def test_includes_standards_checksum(self, tmp_path):
        standards = tmp_path / "standards" / "compiled"
        standards.mkdir(parents=True)
        (standards / "security.json").write_text('{"id":"security"}')
        fp = build_fingerprint(src=tmp_path, files=[], dimension="security", standards_dir=tmp_path / "standards")
        assert fp["standards_checksum"] is not None
        assert len(fp["standards_checksum"]) == 64

    def test_no_standards_dir(self, tmp_path):
        fp = build_fingerprint(src=tmp_path, files=[], dimension="security", standards_dir=None)
        assert fp["standards_checksum"] is None

    def test_includes_dimension_and_timestamp(self, tmp_path):
        fp = build_fingerprint(src=tmp_path, files=[], dimension="reliability", standards_dir=None)
        assert fp["dimension"] == "reliability"
        assert "timestamp" in fp

    def test_git_commit_included(self, tmp_path):
        fp = build_fingerprint(src=tmp_path, files=[], dimension="security", standards_dir=None)
        assert "git_commit" in fp  # may be None if not a git repo


def test_fingerprint_includes_analyzed_files(tmp_path):
    (tmp_path / "a.py").write_text("print('a')")
    (tmp_path / "b.py").write_text("print('b')")
    fp = build_fingerprint(
        tmp_path, ["a.py", "b.py"], "security", None,
        analyzed_files={"a.py"},
    )
    assert fp["analyzed_files"] == ["a.py"]


def test_fingerprint_without_analyzed_files_defaults_empty(tmp_path):
    (tmp_path / "a.py").write_text("print('a')")
    fp = build_fingerprint(tmp_path, ["a.py"], "security", None)
    assert fp["analyzed_files"] == []


class TestSaveLoadFingerprint:
    def test_round_trip(self, tmp_path):
        fp = {"dimension": "security", "git_commit": "abc", "file_hashes": {"a.py": "hash1"}, "standards_checksum": None, "timestamp": "2026-01-01"}
        save_fingerprint(fp, tmp_path)
        loaded = load_fingerprint(tmp_path, "security")
        assert loaded == fp

    def test_returns_none_when_missing(self, tmp_path):
        assert load_fingerprint(tmp_path, "security") is None
