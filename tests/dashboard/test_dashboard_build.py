import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

_SHA256_HEX_LEN = 64

from quodeq.dashboard._build import (
    compute_source_hash,
    needs_rebuild,
    sync_source_to_workdir,
    _HASH_FILE,
)
from quodeq.dashboard._config import BuildConfig, DashboardConfig, ServerConfig


class TestComputeSourceHash:
    def test_hashes_source_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.js").write_text("console.log('hello')")
        (tmp_path / "package.json").write_text('{"name":"test"}')
        result = compute_source_hash(tmp_path)
        assert isinstance(result, str)
        assert len(result) == _SHA256_HEX_LEN  # SHA-256 hex

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


class TestVersionTriggersRebuild:
    """Verify that a version change triggers a UI rebuild."""

    def test_hash_includes_version(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "package.json").write_text('{}')
        hash_v1 = compute_source_hash(src)
        with patch("quodeq.dashboard._build_hash.__version__", "99.0.0"):
            hash_v2 = compute_source_hash(src)
        assert hash_v1 != hash_v2

    def test_version_change_triggers_rebuild(self, tmp_path):
        """Simulates a version upgrade: same source files, different __version__."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "package.json").write_text('{}')
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("ok")
        # Write hash for current version
        current_hash = compute_source_hash(src)
        (static / _HASH_FILE).write_text(current_hash)
        assert needs_rebuild(src, static, False) is False
        # Simulate version upgrade
        with patch("quodeq.dashboard._build_hash.__version__", "99.0.0"):
            assert needs_rebuild(src, static, False) is True


class TestStaticDistDefaulted:
    """Verify that the runner calls maybe_build_ui when static_dist is defaulted."""

    def _make_config(self, tmp_path, static_dist_defaulted=True, no_build=True):
        static = tmp_path / "static"
        static.mkdir(parents=True, exist_ok=True)
        (static / "index.html").write_text("ok")
        reports = tmp_path / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        return DashboardConfig(
            server=ServerConfig(port=4173),
            build=BuildConfig(open_browser=False, no_build=no_build, reinstall=False),
            reports_dir=reports,
            static_dist=static,
            repo_root=tmp_path,
            static_dist_defaulted=static_dist_defaulted,
        )

    def test_defaulted_calls_maybe_build_ui(self, tmp_path, monkeypatch):
        from quodeq.dashboard import runner
        from quodeq.dashboard import _server as _server_mod
        from tests.conftest import DummyProcess

        build_called = []
        static = tmp_path / "static"

        def fake_build(*args, **kwargs):
            build_called.append(True)
            return static

        config = self._make_config(tmp_path, static_dist_defaulted=True, no_build=False)
        monkeypatch.setattr(runner, "maybe_build_ui", fake_build)
        monkeypatch.setattr(runner, "check_dashboard_prereqs", lambda: None)
        monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *a, **k: None)
        monkeypatch.setattr(
            runner, "_ensure_action_api",
            lambda *a, **k: ("http://127.0.0.1:4173", DummyProcess()),
        )
        monkeypatch.setattr(_server_mod, "serve_and_wait", lambda *a: None)

        runner.run_dashboard(config)
        assert build_called, "maybe_build_ui should be called when static_dist is defaulted"

    def test_explicit_static_dist_skips_build(self, tmp_path, monkeypatch):
        from quodeq.dashboard import runner
        from quodeq.dashboard import _server as _server_mod
        from tests.conftest import DummyProcess

        build_called = []

        def fake_build(*args, **kwargs):
            build_called.append(True)
            return tmp_path / "static"

        config = self._make_config(tmp_path, static_dist_defaulted=False)
        monkeypatch.setattr(runner, "maybe_build_ui", fake_build)
        monkeypatch.setattr(runner, "check_dashboard_prereqs", lambda: None)
        monkeypatch.setattr(runner, "_kill_stale_action_api", lambda *a, **k: None)
        monkeypatch.setattr(
            runner, "_ensure_action_api",
            lambda *a, **k: ("http://127.0.0.1:4173", DummyProcess()),
        )
        monkeypatch.setattr(_server_mod, "serve_and_wait", lambda *a: None)

        runner.run_dashboard(config)
        assert not build_called, "maybe_build_ui should not be called when --static-dist is explicit"

    def test_cli_sets_defaulted_flag(self):
        from quodeq.dashboard.cli import parse_args
        config = parse_args(["--port", "4173"])
        assert config.static_dist_defaulted is True

    def test_cli_explicit_clears_defaulted_flag(self, tmp_path):
        from quodeq.dashboard.cli import parse_args
        config = parse_args(["--static-dist", str(tmp_path)])
        assert config.static_dist_defaulted is False
