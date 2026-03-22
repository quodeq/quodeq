import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.dashboard._build import (
    compute_source_hash,
    needs_rebuild,
    sync_source_to_workdir,
    _HASH_FILE,
)


class TestComputeSourceHash:
    def test_hashes_source_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.js").write_text("console.log('hello')")
        (tmp_path / "package.json").write_text('{"name":"test"}')
        result = compute_source_hash(tmp_path)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_hash_changes_when_source_changes(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.js").write_text("v1")
        (tmp_path / "package.json").write_text('{}')
        hash1 = compute_source_hash(tmp_path)
        (src / "app.js").write_text("v2")
        hash2 = compute_source_hash(tmp_path)
        assert hash1 != hash2


class TestNeedsRebuild:
    def test_no_index_html_needs_rebuild(self, tmp_path):
        assert needs_rebuild(tmp_path / "src", tmp_path / "static", False) is True

    def test_no_hash_file_needs_rebuild(self, tmp_path):
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("ok")
        src = tmp_path / "src"
        src.mkdir()
        (src / "package.json").write_text('{}')
        assert needs_rebuild(src, static, False) is True

    def test_matching_hash_skips_rebuild(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "package.json").write_text('{}')
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("ok")
        current_hash = compute_source_hash(src)
        (static / _HASH_FILE).write_text(current_hash)
        assert needs_rebuild(src, static, False) is False

    def test_reinstall_forces_rebuild(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "package.json").write_text('{}')
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("ok")
        current_hash = compute_source_hash(src)
        (static / _HASH_FILE).write_text(current_hash)
        assert needs_rebuild(src, static, True) is True


class TestSyncSourceToWorkdir:
    def test_copies_source_files_preserving_node_modules(self, tmp_path):
        pkg_src = tmp_path / "pkg_src"
        pkg_src.mkdir()
        (pkg_src / "package.json").write_text('{"name":"test"}')
        (pkg_src / "vite.config.js").write_text("export default {}")
        src_dir = pkg_src / "src"
        src_dir.mkdir()
        (src_dir / "App.jsx").write_text("function App() {}")

        workdir = tmp_path / "workdir"
        workdir.mkdir()
        nm = workdir / "node_modules"
        nm.mkdir()
        (nm / "react").mkdir()
        (nm / "react" / "index.js").write_text("module.exports = {}")

        sync_source_to_workdir(pkg_src, workdir)

        assert (workdir / "package.json").read_text() == '{"name":"test"}'
        assert (workdir / "src" / "App.jsx").read_text() == "function App() {}"
        assert (workdir / "node_modules" / "react" / "index.js").exists()
