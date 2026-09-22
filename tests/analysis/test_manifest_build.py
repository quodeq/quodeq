"""Tests for the source manifest builder — basic single-scope build behavior.

Split from test_manifest.py. Shared `detection` fixture lives in
tests/analysis/_manifest_fixtures.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.manifest import build_manifest

from tests.analysis._manifest_fixtures import detection  # noqa: F401 -- pytest fixture


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


def test_analysis_target_name_with_category() -> None:
    from quodeq.analysis.manifest import target_name
    assert target_name("rust", "backend") == "rust_backend"
    assert target_name("python", None) == "python"
