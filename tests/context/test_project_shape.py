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
    # Both signals present -> desktop wins outright (see _python_signals).
    # This assertion used to be UNKNOWN, which was the bug: it made
    # detect_shape discard a manifest that unambiguously ships a desktop
    # app just because a web framework also showed up as a dev dependency.
    assert shape.deployment is Deployment.DESKTOP


def test_desktop_beats_web_in_one_manifest(tmp_path):
    """A desktop app that embeds a web framework is DESKTOP, not UNKNOWN.

    detect_shape's own comment says desktop signals beat web signals because
    web hints show up in the dev dependencies of desktop apps. That priority
    was unreachable: _python_signals collapsed the both-present case to None.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "app"\n'
        'dependencies = ["flask>=3.0", "pywebview>=6.2"]\n',
        encoding="utf-8",
    )
    shape = detect_shape(tmp_path)
    assert shape.deployment is Deployment.DESKTOP
    assert shape.is_single_user is True
    # The web framework is still reported; it is context, not a verdict.
    assert "flask" in shape.web_frameworks


def test_web_only_manifest_still_web_service(tmp_path):
    """Guard against over-correcting: no desktop hint means no desktop verdict."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "svc"\ndependencies = ["flask>=3.0"]\n',
        encoding="utf-8",
    )
    assert detect_shape(tmp_path).deployment is Deployment.WEB_SERVICE


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


class TestPathologicalManifestsDegrade:
    """detect_shape must never fail a scan over a manifest it cannot read.

    Its contract is "fall back to UNKNOWN whenever signals are absent or
    contradictory", and four callers (_api_runner, api_prompt_assembly,
    mcp/findings_server, and context/__init__'s re-export) invoke it with no
    guard of their own. Anything that escapes here fails the run.

    The manifests below are all *analyzed*, untrusted input from the repo
    under evaluation, not files Quodeq controls.
    """

    def test_deeply_nested_package_json(self, tmp_path: Path, deeply_nested_json: str) -> None:
        # _read_json caught only json.JSONDecodeError. Nesting deep enough to
        # exhaust the C decoder's call stack raises RecursionError instead --
        # a RuntimeError subclass, so it escaped.
        _write(tmp_path / "package.json", deeply_nested_json)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_deeply_nested_pyproject_toml(self, tmp_path: Path) -> None:
        # Same class through tomllib, which is a pure-Python recursive-descent
        # parser and so overflows at a much shallower depth than the C JSON
        # decoder. _read_toml caught only OSError/TOMLDecodeError.
        _write(tmp_path / "pyproject.toml", "a = " + "[" * 5000 + "]" * 5000)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_deeply_nested_cargo_toml(self, tmp_path: Path) -> None:
        # _rust_signals shares _read_toml, so Cargo.toml is the same hole.
        _write(tmp_path / "Cargo.toml", "a = " + "[" * 5000 + "]" * 5000)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_dependencies_that_are_not_a_list(self, tmp_path: Path) -> None:
        """Not a RecursionError, and not fixed by widening the readers.

        ``dependencies = 5`` parses as perfectly valid TOML, so every reader
        succeeds; _python_signals then did ``list(deps_list)`` on an int and
        raised TypeError. Guarding only the readers would leave this escape
        open, which is the whole point of fixing detect_shape at the source
        rather than wrapping each caller.
        """
        _write(tmp_path / "pyproject.toml", '[project]\nname = "x"\ndependencies = 5\n')
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_a_readable_manifest_still_detects_after_a_broken_sibling(
        self, tmp_path: Path, deeply_nested_json: str,
    ) -> None:
        """Degrading is per-manifest, not all-or-nothing.

        A pathological package.json must not blank the verdict a perfectly
        good pyproject.toml supports -- otherwise the fix trades a crash for
        silent, total detection loss.
        """
        _write(tmp_path / "package.json", deeply_nested_json)
        _write(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\ndependencies = ["flask>=3.0"]\n',
        )
        shape = detect_shape(tmp_path)
        assert shape.deployment is Deployment.WEB_SERVICE
        assert shape.web_frameworks == ["flask"]
