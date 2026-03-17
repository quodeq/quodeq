"""Tests for universal language detection using detection.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.plugins.detector import detect_language
from quodeq.config.paths import default_paths


@pytest.fixture()
def detection_file() -> Path:
    path = default_paths().detection_file
    if not path.exists():
        pytest.skip("detection.json not installed")
    return path


def test_detection_file_loads(detection_file: Path) -> None:
    data = json.loads(detection_file.read_text())
    assert "extensions" in data
    assert "config_files" in data
    assert "skip_dirs" in data


def test_detection_file_has_common_languages(detection_file: Path) -> None:
    data = json.loads(detection_file.read_text())
    exts = data["extensions"]
    assert exts[".py"] == "python"
    assert exts[".ts"] == "typescript"
    assert exts[".java"] == "java"
    assert exts[".swift"] == "swift"
    assert exts[".go"] == "go"
    assert exts[".rs"] == "rust"


def test_detect_python_by_config(tmp_path: Path, detection_file: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
    lang = detect_language(tmp_path, detection_file)
    assert lang == "python"


def test_detect_typescript_by_extension(tmp_path: Path, detection_file: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.ts").write_text("const x = 1;\n")
    (src / "util.ts").write_text("export const y = 2;\n")
    lang = detect_language(tmp_path, detection_file)
    assert lang == "typescript"


def test_detect_java_by_config(tmp_path: Path, detection_file: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project></project>")
    lang = detect_language(tmp_path, detection_file)
    assert lang == "java"


def test_detect_no_match_raises(tmp_path: Path, detection_file: Path) -> None:
    with pytest.raises(ValueError, match="No language detected"):
        detect_language(tmp_path, detection_file)


def test_detect_primary_language_by_count(tmp_path: Path, detection_file: Path) -> None:
    """When multiple languages exist, primary is the one with more files."""
    src = tmp_path / "src"
    src.mkdir()
    for i in range(5):
        (src / f"mod{i}.py").write_text(f"x = {i}\n")
    (src / "helper.ts").write_text("export default {}\n")
    lang = detect_language(tmp_path, detection_file)
    assert lang == "python"
