"""Tests for the source manifest builder."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis.manifest import AnalysisTarget, SourceManifest, build_manifest


@pytest.fixture()
def detection() -> dict:
    return {
        "extensions": {
            ".py": "python",
            ".ts": "typescript",
            ".js": "javascript",
            ".java": "java",
        },
        "skip_dirs": ["node_modules", "__pycache__", ".git", "dist"],
        "config_files": {
            "pyproject.toml": "python",
            "tsconfig.json": "typescript",
        },
        "skip_patterns": ["*.min.js"],
    }


def test_build_empty_repo(tmp_path: Path, detection: dict) -> None:
    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 0
    assert manifest.source_files == []
    assert manifest.language == "unknown"
    assert manifest.targets == []


def test_build_python_repo(tmp_path: Path, detection: dict) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hello')\n")
    (src / "util.py").write_text("def f(): pass\n")
    (src / "extra.py").write_text("x = 1\n")
    (src / "readme.txt").write_text("not a source file\n")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.language == "python"
    assert manifest.total_files == 3
    assert len(manifest.source_files) == 3
    assert ".py" in manifest.language_stats
    assert manifest.language_stats[".py"] == 3
    assert len(manifest.targets) == 1
    assert manifest.targets[0].language == "python"


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


def test_multi_language_detection(tmp_path: Path, detection: dict) -> None:
    for i in range(5):
        (tmp_path / f"mod{i}.py").write_text(f"x = {i}\n")
    for i in range(3):
        (tmp_path / f"app{i}.ts").write_text(f"const y = {i};\n")

    manifest = build_manifest(tmp_path, detection)
    # Primary target should be python (most files)
    assert manifest.language == "python"
    assert manifest.language_stats[".py"] == 5
    assert manifest.language_stats[".ts"] == 3
    # Should have two targets
    assert len(manifest.targets) == 2
    langs = {t.language for t in manifest.targets}
    assert langs == {"python", "typescript"}


def test_small_language_excluded(tmp_path: Path, detection: dict) -> None:
    """Languages with fewer than 3 files are excluded as noise."""
    for i in range(5):
        (tmp_path / f"mod{i}.py").write_text(f"x = {i}\n")
    (tmp_path / "app.ts").write_text("const y = 1;\n")

    manifest = build_manifest(tmp_path, detection)
    assert len(manifest.targets) == 1
    assert manifest.targets[0].language == "python"


def test_source_files_sorted(tmp_path: Path, detection: dict) -> None:
    (tmp_path / "z.py").write_text("")
    (tmp_path / "a.py").write_text("")
    (tmp_path / "m.py").write_text("")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.source_files == ["a.py", "m.py", "z.py"]


def test_to_prompt_context(detection: dict) -> None:
    target = AnalysisTarget(
        name="python_backend",
        language="python",
        category="backend",
        frameworks=["Django", "REST"],
        total_files=42,
        source_files=["a.py"],
        language_stats={".py": 42},
    )
    manifest = SourceManifest(targets=[target], total_files=42, language_stats={".py": 42})
    text = manifest.to_prompt_context()
    assert "Python" in text
    assert "42" in text
    assert "backend" in text
    assert "Django" in text


def test_to_dict(detection: dict) -> None:
    target = AnalysisTarget(
        name="typescript",
        language="typescript",
        total_files=10,
        source_files=["a.ts", "b.ts"],
        language_stats={".ts": 10},
    )
    manifest = SourceManifest(targets=[target], total_files=10, language_stats={".ts": 10})
    d = manifest.to_dict()
    assert d["language"] == "typescript"
    assert d["total_files"] == 10
    assert d["source_files_count"] == 2
    assert len(d["targets"]) == 1


def test_with_disciplines_conf(tmp_path: Path, detection: dict) -> None:
    """build_manifest picks up category and topics from disciplines.conf."""
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        "[python_fullstack]\n"
        "language=python\n"
        "category=backend\n"
        "detect_file=pyproject.toml\n"
        "detect_priority=6\n"
        "suggested_topics=Django,FastAPI\n"
    )
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    for i in range(3):
        (tmp_path / f"app{i}.py").write_text(f"import flask  # {i}\n")

    manifest = build_manifest(tmp_path, detection, disciplines_conf=conf)
    assert manifest.language == "python"
    assert manifest.category == "backend"
    assert "Django" in manifest.frameworks


def test_multi_target_prompt_context() -> None:
    """Multi-target manifest renders detected modules in prompt context."""
    rust = AnalysisTarget(
        name="rust_backend", language="rust", category="backend",
        total_files=85, source_files=["main.rs"],
        language_stats={".rs": 85},
    )
    dart = AnalysisTarget(
        name="dart_mobile", language="dart", category="mobile",
        frameworks=["Flutter"], total_files=235, source_files=["main.dart"],
        language_stats={".dart": 235},
    )
    manifest = SourceManifest(targets=[dart, rust], total_files=320, language_stats={".rs": 85, ".dart": 235})
    text = manifest.to_prompt_context()
    assert "320" in text
    assert "Detected modules" in text
    assert "Dart mobile" in text
    assert "Flutter" in text
    assert "Rust backend" in text
    assert "each file according to its language" in text


def test_analysis_target_name_with_category() -> None:
    from quodeq.analysis.manifest import target_name
    assert target_name("rust", "backend") == "rust_backend"
    assert target_name("python", None) == "python"


# --- Monorepo / recursive subproject discovery ----------------------------------


def _write(p: Path, body: str = "") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_build_monorepo_partitions_files_by_subproject(
    tmp_path: Path, detection: dict,
) -> None:
    """A monorepo with subprojects under apps/* and services/* must produce one
    scoped target per subproject, with each subproject's files routed to its own
    target. Files outside any subproject are dropped (they don't belong to any
    classified project)."""
    from quodeq.config.paths import default_paths

    # services/api → Flask (Python)
    _write(
        tmp_path / "services/api/pyproject.toml",
        '[project]\nname = "api"\ndependencies = ["flask==3.1.3"]\n',
    )
    _write(tmp_path / "services/api/src/api/__init__.py", "")
    _write(tmp_path / "services/api/src/api/main.py", "from flask import Flask\n")
    _write(tmp_path / "services/api/src/api/routes.py", "from flask import Blueprint\n")

    # apps/web → React (TypeScript)
    _write(
        tmp_path / "apps/web/package.json",
        '{"name":"web","dependencies":{"react":"^18.0.0","react-dom":"^18.0.0"}}',
    )
    _write(tmp_path / "apps/web/tsconfig.json", "{}")
    _write(tmp_path / "apps/web/src/App.ts", "export const App = () => null;\n")
    _write(tmp_path / "apps/web/src/index.ts", "import {App} from './App';\n")
    _write(tmp_path / "apps/web/src/util.ts", "export const noop = () => {};\n")

    # README at root and stray .py — outside any subproject scope, must be dropped.
    _write(tmp_path / "README.md", "# monorepo\n")
    _write(tmp_path / "scripts/orphan.py", "print('orphan')\n")

    disciplines_conf = default_paths().disciplines_conf
    if not disciplines_conf.exists():
        pytest.skip("disciplines.conf not installed")

    manifest = build_manifest(tmp_path, detection, disciplines_conf=disciplines_conf)

    scopes = sorted(t.scope_path for t in manifest.targets)
    assert scopes == ["apps/web", "services/api"]

    by_scope = {t.scope_path: t for t in manifest.targets}

    api = by_scope["services/api"]
    assert api.language == "python"
    assert "Flask Best Practices" in api.frameworks
    assert all(f.startswith("services/api/") for f in api.source_files)
    assert all("apps/web" not in f for f in api.source_files)

    web = by_scope["apps/web"]
    assert web.language == "typescript"
    assert "React Best Practices" in web.frameworks
    assert all(f.startswith("apps/web/") for f in web.source_files)


def test_monorepo_walk_applies_skip_patterns(tmp_path: Path, detection: dict) -> None:
    """The multi-scope (monorepo) walk honours skip_patterns too."""
    from quodeq.config.paths import default_paths

    _write(
        tmp_path / "apps/web/package.json",
        '{"name":"web","dependencies":{"react":"^18.0.0","react-dom":"^18.0.0"}}',
    )
    _write(tmp_path / "apps/web/tsconfig.json", "{}")
    _write(tmp_path / "apps/web/src/App.ts", "export const App = () => null;\n")
    _write(tmp_path / "apps/web/src/index.ts", "import {App} from './App';\n")
    _write(tmp_path / "apps/web/src/util.ts", "export const noop = () => {};\n")
    _write(tmp_path / "apps/web/src/vendor.min.js", "var a=1;")

    _write(
        tmp_path / "services/api/pyproject.toml",
        '[project]\nname = "api"\ndependencies = ["flask==3.1.3"]\n',
    )
    _write(tmp_path / "services/api/src/api/__init__.py", "")
    _write(tmp_path / "services/api/src/api/main.py", "from flask import Flask\n")
    _write(tmp_path / "services/api/src/api/routes.py", "from flask import Blueprint\n")

    disciplines_conf = default_paths().disciplines_conf
    if not disciplines_conf.exists():
        pytest.skip("disciplines.conf not installed")

    manifest = build_manifest(tmp_path, detection, disciplines_conf=disciplines_conf)

    all_files = [f for t in manifest.targets for f in t.source_files]
    assert "apps/web/src/vendor.min.js" not in all_files


def test_build_single_root_project_uses_legacy_path(
    tmp_path: Path, detection: dict,
) -> None:
    """When recursive discovery returns just the root, behaviour matches the
    pre-monorepo single-scope path: scope_path stays empty and the existing
    single-target manifest shape is preserved."""
    from quodeq.config.paths import default_paths

    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "x"\ndependencies = ["flask==3.1.3"]\n',
    )
    _write(tmp_path / "src/app/__init__.py", "")
    _write(tmp_path / "src/app/main.py", "from flask import Flask\n")
    _write(tmp_path / "src/app/util.py", "def f(): pass\n")

    disciplines_conf = default_paths().disciplines_conf
    if not disciplines_conf.exists():
        pytest.skip("disciplines.conf not installed")

    manifest = build_manifest(tmp_path, detection, disciplines_conf=disciplines_conf)

    assert all(t.scope_path == "" for t in manifest.targets)
    primary = manifest.targets[0]
    assert primary.language == "python"
    assert "Flask Best Practices" in primary.frameworks


def test_build_explicit_scope_skips_recursive_discovery(
    tmp_path: Path, detection: dict,
) -> None:
    """An explicit caller-provided scope_path bypasses recursive discovery — the
    caller has pinned analysis to that subdir."""
    from quodeq.config.paths import default_paths

    _write(
        tmp_path / "services/api/pyproject.toml",
        '[project]\nname="api"\ndependencies=["flask==3.1.3"]\n',
    )
    _write(tmp_path / "services/api/src/app/__init__.py", "")
    _write(tmp_path / "services/api/src/app/main.py", "from flask import Flask\n")

    _write(
        tmp_path / "apps/web/package.json",
        '{"name":"web","dependencies":{"react":"^18"}}',
    )
    _write(tmp_path / "apps/web/src/App.ts", "export const App = () => null;\n")

    disciplines_conf = default_paths().disciplines_conf
    if not disciplines_conf.exists():
        pytest.skip("disciplines.conf not installed")

    manifest = build_manifest(
        tmp_path, detection, disciplines_conf=disciplines_conf, scope_path="services/api",
    )

    # Only services/api files are walked; apps/web is invisible.
    assert all("apps/web" not in f for t in manifest.targets for f in t.source_files)
