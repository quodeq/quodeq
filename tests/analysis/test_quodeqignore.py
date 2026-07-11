"""Tests for .quodeqignore repo-local path exclusions."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quodeq.analysis._diff_resolver import resolve_diff_files
from quodeq.analysis._ignore import IGNORE_FILENAME, is_ignored, load_ignore_patterns
from quodeq.analysis.manifest import build_manifest


@pytest.fixture()
def detection() -> dict:
    return {
        "extensions": {
            ".py": "python",
            ".ts": "typescript",
            ".js": "javascript",
        },
        "skip_dirs": ["node_modules", "__pycache__", ".git", "dist"],
    }


def _write(p: Path, body: str = "") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


# --- load_ignore_patterns --------------------------------------------------------


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_ignore_patterns(tmp_path) == []


def test_load_strips_comments_blanks_and_decorations(tmp_path: Path) -> None:
    (tmp_path / IGNORE_FILENAME).write_text(
        "# planted-bug corpus\n"
        "\n"
        "benchmarks/corpus/\n"
        "  fixtures  \n"
        "./generated\n",
        encoding="utf-8",
    )
    assert load_ignore_patterns(tmp_path) == ["benchmarks/corpus", "fixtures", "generated"]


def test_load_undecodable_file_treated_as_empty(tmp_path: Path) -> None:
    (tmp_path / IGNORE_FILENAME).write_bytes(b"\xff\xfe garbage \x00")
    assert load_ignore_patterns(tmp_path) == []


# --- is_ignored ------------------------------------------------------------------


def test_is_ignored_exact_file() -> None:
    assert is_ignored("src/legacy.py", ["src/legacy.py"])


def test_is_ignored_directory_prefix_covers_contents() -> None:
    patterns = ["benchmarks/corpus"]
    assert is_ignored("benchmarks/corpus", patterns)
    assert is_ignored("benchmarks/corpus/deep/planted.py", patterns)
    assert not is_ignored("benchmarks/harness.py", patterns)


def test_is_ignored_glob_crosses_directories() -> None:
    assert is_ignored("a/b/bundle.min.js", ["*.min.js"])
    assert not is_ignored("a/b/bundle.js", ["*.min.js"])


def test_is_ignored_no_partial_name_match() -> None:
    # "fixtures" must not swallow "fixtures_util.py" or "src/fixtures2/x.py".
    assert not is_ignored("fixtures_util.py", ["fixtures"])
    assert not is_ignored("src/fixtures2/x.py", ["fixtures"])


def test_is_ignored_empty_patterns() -> None:
    assert not is_ignored("anything.py", [])


# --- build_manifest integration ---------------------------------------------------


def test_manifest_excludes_ignored_directory(tmp_path: Path, detection: dict) -> None:
    _write(tmp_path / IGNORE_FILENAME, "corpus/\n")
    _write(tmp_path / "corpus" / "planted.py", "import pickle  # planted bug\n")
    _write(tmp_path / "corpus" / "deep" / "worse.py", "eval('x')\n")
    for i in range(3):
        _write(tmp_path / f"app{i}.py", f"x = {i}\n")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 3
    assert all("corpus" not in f for f in manifest.source_files)


def test_manifest_excludes_glob_pattern(tmp_path: Path, detection: dict) -> None:
    _write(tmp_path / IGNORE_FILENAME, "*.gen.py\n")
    _write(tmp_path / "src" / "schema.gen.py", "# generated\n")
    for i in range(3):
        _write(tmp_path / "src" / f"app{i}.py", f"x = {i}\n")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 3
    assert "src/schema.gen.py" not in manifest.source_files


def test_manifest_without_ignore_file_unchanged(tmp_path: Path, detection: dict) -> None:
    _write(tmp_path / "corpus" / "planted.py", "x = 1\n")
    for i in range(3):
        _write(tmp_path / f"app{i}.py", f"x = {i}\n")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 4
    assert "corpus/planted.py" in manifest.source_files


def test_manifest_scoped_walk_honors_ignore(tmp_path: Path, detection: dict) -> None:
    """Patterns are anchored at the scan root even when a scope_path is pinned."""
    _write(tmp_path / IGNORE_FILENAME, "pkg/generated\n")
    _write(tmp_path / "pkg" / "generated" / "stub.py", "# generated\n")
    for i in range(3):
        _write(tmp_path / "pkg" / f"mod{i}.py", f"x = {i}\n")

    manifest = build_manifest(tmp_path, detection, scope_path="pkg")
    assert manifest.total_files == 3
    assert all(not f.startswith("pkg/generated/") for f in manifest.source_files)


def test_manifest_monorepo_walk_honors_ignore(tmp_path: Path, detection: dict) -> None:
    """The multi-scope (monorepo) walk applies .quodeqignore too."""
    from quodeq.config.paths import default_paths

    disciplines_conf = default_paths().disciplines_conf
    if not disciplines_conf.exists():
        pytest.skip("disciplines.conf not installed")

    _write(tmp_path / IGNORE_FILENAME, "services/api/testdata/\n")
    _write(
        tmp_path / "services/api/pyproject.toml",
        '[project]\nname = "api"\ndependencies = ["flask==3.1.3"]\n',
    )
    _write(tmp_path / "services/api/src/api/__init__.py", "")
    _write(tmp_path / "services/api/src/api/main.py", "from flask import Flask\n")
    _write(tmp_path / "services/api/src/api/routes.py", "from flask import Blueprint\n")
    _write(tmp_path / "services/api/testdata/planted.py", "eval('x')\n")

    _write(
        tmp_path / "apps/web/package.json",
        '{"name":"web","dependencies":{"react":"^18.0.0","react-dom":"^18.0.0"}}',
    )
    _write(tmp_path / "apps/web/tsconfig.json", "{}")
    _write(tmp_path / "apps/web/src/App.ts", "export const App = () => null;\n")
    _write(tmp_path / "apps/web/src/index.ts", "import {App} from './App';\n")
    _write(tmp_path / "apps/web/src/util.ts", "export const noop = () => {};\n")

    manifest = build_manifest(tmp_path, detection, disciplines_conf=disciplines_conf)
    all_files = [f for t in manifest.targets for f in t.source_files]
    assert all_files, "monorepo walk produced no files"
    assert all("testdata" not in f for f in all_files)


# --- diff-mode integration ---------------------------------------------------------


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def test_resolve_diff_files_drops_ignored_paths(tmp_path: Path) -> None:
    """Ignored paths never re-enter analysis via git-diff detection."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    _write(repo / IGNORE_FILENAME, "corpus/\n")
    _write(repo / "app.py", "x = 1\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "base"], repo)
    _run(["git", "checkout", "-q", "-b", "feature"], repo)
    _write(repo / "app.py", "x = 2\n")
    _write(repo / "corpus" / "planted.py", "eval('x')\n")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "change"], repo)

    result = resolve_diff_files(repo, "main")
    assert result == ["app.py"]
