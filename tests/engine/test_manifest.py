"""Tests for the source manifest builder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.manifest import SourceManifest, build_manifest


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


def test_build_python_repo(tmp_path: Path, detection: dict) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hello')\n")
    (src / "util.py").write_text("def f(): pass\n")
    (src / "readme.txt").write_text("not a source file\n")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.language == "python"
    assert manifest.total_files == 2
    assert len(manifest.source_files) == 2
    assert ".py" in manifest.language_stats
    assert manifest.language_stats[".py"] == 2


def test_skips_excluded_dirs(tmp_path: Path, detection: dict) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.js").write_text("// vendored")
    (tmp_path / "app.js").write_text("const x = 1;")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.total_files == 1
    assert manifest.language == "javascript"


def test_multi_language_detection(tmp_path: Path, detection: dict) -> None:
    for i in range(3):
        (tmp_path / f"mod{i}.py").write_text(f"x = {i}\n")
    (tmp_path / "app.ts").write_text("const y = 1;\n")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.language == "python"
    assert manifest.language_stats[".py"] == 3
    assert manifest.language_stats[".ts"] == 1


def test_source_files_sorted(tmp_path: Path, detection: dict) -> None:
    (tmp_path / "z.py").write_text("")
    (tmp_path / "a.py").write_text("")
    (tmp_path / "m.py").write_text("")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.source_files == ["a.py", "m.py", "z.py"]


def test_to_prompt_context(detection: dict) -> None:
    manifest = SourceManifest(
        language="python",
        category="backend",
        frameworks=["Django", "REST"],
        total_files=42,
        source_files=["a.py"],
        language_stats={".py": 42},
    )
    text = manifest.to_prompt_context()
    assert "python" in text
    assert "42" in text
    assert "backend" in text
    assert "Django" in text


def test_to_dict(detection: dict) -> None:
    manifest = SourceManifest(
        language="typescript",
        total_files=10,
        source_files=["a.ts", "b.ts"],
        language_stats={".ts": 10},
    )
    d = manifest.to_dict()
    assert d["language"] == "typescript"
    assert d["total_files"] == 10
    assert d["source_files_count"] == 2


def test_with_disciplines_conf(tmp_path: Path, detection: dict) -> None:
    """build_manifest picks up category and topics from disciplines.conf."""
    # Create a minimal disciplines.conf
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
    (tmp_path / "app.py").write_text("import flask\n")

    manifest = build_manifest(tmp_path, detection, disciplines_conf=conf)
    assert manifest.language == "python"
    assert manifest.category == "backend"
    assert "Django" in manifest.frameworks
