"""Tests for the source manifest builder — monorepo / recursive subproject
discovery.

Split from test_manifest.py. Shared `detection` fixture lives in
tests/analysis/_manifest_fixtures.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis.manifest import build_manifest

from tests.analysis._manifest_fixtures import detection  # noqa: F401 -- pytest fixture


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


def test_monorepo_keeps_source_outside_detected_subprojects(tmp_path: Path) -> None:
    """A repo whose only *detected* subproject is a nested one must not lose the
    source tree living outside it.

    Kotlin Multiplatform is the real-world case: ``iosApp/`` is recognised via
    ``*.xcodeproj``, but the Gradle/Kotlin root is not (its plugins come from a
    version catalog, so no ``com.android`` literal appears in build.gradle.kts).
    Without a catch-all root scope every ``.kt`` file is dropped and the manifest
    comes back empty, which downstream reads as "no source files".
    """
    from quodeq.config.paths import default_paths

    kmp_detection = {
        "extensions": {".kt": "kotlin", ".swift": "swift"},
        "skip_dirs": ["build", ".gradle"],
        "skip_patterns": [],
    }

    _write(tmp_path / "settings.gradle.kts", 'rootProject.name = "app"\n')
    _write(
        tmp_path / "build.gradle.kts",
        "plugins {\n    alias(libs.plugins.androidApplication) apply false\n}\n",
    )
    for name in ("App", "Main", "Repo", "Model"):
        _write(tmp_path / f"composeApp/src/commonMain/kotlin/{name}.kt", "class X\n")

    _write(tmp_path / "iosApp/iosApp.xcodeproj/project.pbxproj", "// pbxproj\n")
    for name in ("ContentView", "iosAppApp", "Theme"):
        _write(tmp_path / f"iosApp/iosApp/{name}.swift", "import SwiftUI\n")

    disciplines_conf = default_paths().disciplines_conf
    if not disciplines_conf.exists():
        pytest.skip("disciplines.conf not installed")

    manifest = build_manifest(tmp_path, kmp_detection, disciplines_conf=disciplines_conf)

    kotlin_files = [
        f for t in manifest.targets if t.language == "kotlin" for f in t.source_files
    ]
    assert len(kotlin_files) == 4
    assert manifest.total_files == 7
    assert manifest.language_stats == {".kt": 4, ".swift": 3}

    swift = next(t for t in manifest.targets if t.language == "swift")
    assert swift.scope_path == "iosApp"


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
