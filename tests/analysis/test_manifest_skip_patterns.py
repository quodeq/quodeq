"""Tests for the source manifest builder — skip_dirs and skip_patterns filtering.

Split from test_manifest.py. Shared `detection` fixture lives in
tests/analysis/_manifest_fixtures.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.manifest import build_manifest

from tests.analysis._manifest_fixtures import detection  # noqa: F401 -- pytest fixture


def test_skips_excluded_dirs(tmp_path: Path, detection: dict) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("// vendored")
    for i in range(3):
        (tmp_path / f"app{i}.js").write_text(f"const x = {i};")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 3
    assert manifest.language == "javascript"


def test_skip_patterns_exclude_matching_files(tmp_path: Path, detection: dict) -> None:
    """Files matching a skip_patterns glob are excluded from the manifest."""
    for i in range(3):
        (tmp_path / f"app{i}.js").write_text(f"const x = {i};")
    (tmp_path / "bundle.min.js").write_text("var a=1;var b=2;")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 3
    assert "bundle.min.js" not in manifest.source_files


def test_skip_patterns_match_at_any_depth(tmp_path: Path, detection: dict) -> None:
    """skip_patterns apply to files in nested directories, not just the root."""
    sub = tmp_path / "assets" / "js"
    sub.mkdir(parents=True)
    (sub / "lib.min.js").write_text("var a=1;")
    for i in range(3):
        (tmp_path / f"app{i}.js").write_text(f"const x = {i};")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 3
    assert "assets/js/lib.min.js" not in manifest.source_files


def test_missing_skip_patterns_key_includes_all_files(tmp_path: Path, detection: dict) -> None:
    """Without a skip_patterns key, no file-level filtering happens."""
    del detection["skip_patterns"]
    for i in range(3):
        (tmp_path / f"app{i}.js").write_text(f"const x = {i};")
    (tmp_path / "bundle.min.js").write_text("var a=1;")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 4
    assert "bundle.min.js" in manifest.source_files
