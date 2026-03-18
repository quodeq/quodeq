"""Tests for the source manifest builder."""
from __future__ import annotations

import json
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
    from quodeq.analysis.manifest import _target_name
    assert _target_name("rust", "backend") == "rust_backend"
    assert _target_name("python", None) == "python"
