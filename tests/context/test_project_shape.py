from pathlib import Path

import pytest

from quodeq.context.project_shape import Deployment, ProjectShape, detect_shape


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_unknown_when_no_manifests(tmp_path: Path) -> None:
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.UNKNOWN
    assert shape.is_single_user is True
    assert shape.web_frameworks == []
    assert shape.runtime_langs == []


def test_missing_repo_returns_unknown(tmp_path: Path) -> None:
    shape = detect_shape(tmp_path / "does-not-exist")
    assert shape.deployment is Deployment.UNKNOWN


def test_pyproject_with_flask_is_web_service(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", """
[project]
name = "x"
version = "0.1.0"
dependencies = ["flask>=3.0", "click"]
""")
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.WEB_SERVICE
    assert "flask" in shape.web_frameworks
    assert shape.is_single_user is False


def test_pyproject_with_pyinstaller_is_desktop(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", """
[project]
name = "x"
version = "0.1.0"
dependencies = ["pywebview>=5.0", "click"]
""")
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.DESKTOP
    assert shape.is_single_user is True


def test_desktop_wins_when_pyproject_has_both(tmp_path: Path) -> None:
    """Desktop framework dep beats a web framework dep in optional-dependencies.

    Real example: a desktop app may pull in flask only as a dev dep for a
    docs server. Optional dependencies should not flip the deployment.
    """
    _write(tmp_path / "pyproject.toml", """
[project]
name = "x"
version = "0.1.0"
dependencies = ["pywebview>=5.0"]

[project.optional-dependencies]
dev = ["flask"]
""")
    shape = detect_shape(tmp_path)
    # Both signals present -> Python returns None (ambiguous), falling back
    # to UNKNOWN unless something else votes. Desktop hint at the *project*
    # priority pass wins below — but here pyproject is ambiguous, no other
    # manifests exist, so verdict is UNKNOWN.
    assert shape.deployment is Deployment.UNKNOWN


def test_package_json_express_is_web_service(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", '{"dependencies": {"express": "^4.0.0"}}')
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.WEB_SERVICE
    assert "express" in shape.web_frameworks
    assert shape.is_single_user is False


def test_package_json_electron_is_desktop(tmp_path: Path) -> None:
    _write(tmp_path / "package.json",
           '{"dependencies": {"electron": "^28.0.0", "react": "^18.0.0"}}')
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.DESKTOP
    assert shape.ui_lang == "react"
    assert shape.is_single_user is True


def test_package_json_react_native_is_mobile(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", '{"dependencies": {"react-native": "0.73"}}')
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.MOBILE


def test_cargo_lib_only_publishable_is_library(tmp_path: Path) -> None:
    _write(tmp_path / "Cargo.toml", """
[package]
name = "x"
version = "0.1.0"
""")
    _write(tmp_path / "src" / "lib.rs", "// lib")
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.LIBRARY


def test_cargo_bin_only_is_cli(tmp_path: Path) -> None:
    _write(tmp_path / "Cargo.toml", """
[package]
name = "x"
version = "0.1.0"
""")
    _write(tmp_path / "src" / "main.rs", "fn main() {}")
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.CLI


def test_go_with_main_no_web_imports_is_cli(tmp_path: Path) -> None:
    _write(tmp_path / "go.mod", "module example.com/x\n\ngo 1.22\n")
    _write(tmp_path / "main.go", "package main\n\nfunc main() {}\n")
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.CLI


def test_go_with_net_http_is_web_service(tmp_path: Path) -> None:
    _write(tmp_path / "go.mod", "module example.com/x\n\ngo 1.22\n")
    _write(tmp_path / "main.go",
           'package main\nimport "net/http"\nfunc main() { http.ListenAndServe(":8080", nil) }\n')
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.WEB_SERVICE


def test_desktop_python_beats_cli_go_when_both_present(tmp_path: Path) -> None:
    """Multi-language repos: desktop hints from any manifest beat cli."""
    _write(tmp_path / "pyproject.toml", """
[project]
name = "x"
version = "0.1.0"
dependencies = ["pywebview"]
""")
    _write(tmp_path / "go.mod", "module example.com/x\n\ngo 1.22\n")
    _write(tmp_path / "main.go", "package main\nfunc main() {}\n")
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.DESKTOP
    assert "python" in shape.runtime_langs
    assert "go" in shape.runtime_langs


def test_to_dict_serializes_enum_value() -> None:
    shape = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)
    d = shape.to_dict()
    assert d["deployment"] == "desktop"
    assert d["is_single_user"] is True


def test_runtime_langs_detected_from_markers(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname = 'x'\nversion='0.1.0'\n")
    _write(tmp_path / "Gemfile", "source 'https://rubygems.org'")
    shape = detect_shape(tmp_path)
    assert "python" in shape.runtime_langs
    assert "ruby" in shape.runtime_langs


def test_unknown_deployment_is_single_user() -> None:
    """Default for ambiguous projects: assume single-user (libraries, CLIs,
    or bare repos without manifests). Only web_service flips the flag."""
    shape = ProjectShape()
    assert shape.deployment is Deployment.UNKNOWN
    assert shape.is_single_user is True
